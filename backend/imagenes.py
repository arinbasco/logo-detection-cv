"""Imágenes: reducir, codificar en JPEG, recortar cajas y validar fotogramas del modo en vivo."""

import os

LADO_MAXIMO_EN_VIVO = 1920
# Igual que en la API del modelo: OpenCV se niega a decodificar imágenes con más píxeles
# que este límite, así que una imagen pequeña en bytes pero enorme en píxeles no agota la
# memoria. Tiene que fijarse antes de importar cv2.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(LADO_MAXIMO_EN_VIVO * LADO_MAXIMO_EN_VIVO))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

LADO_MODELO = 640  # el tamaño con el que trabaja el modelo
LADO_RECORTE = 256

FIRMA_JPEG = b"\xff\xd8\xff"
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"


class ImagenNoAdmitida(Exception):
    """El archivo no es un JPEG ni un PNG válido."""


class ImagenDemasiadoGrande(Exception):
    """La imagen mide más de 1920 píxeles de lado."""


def reducir(imagen: np.ndarray, lado_maximo: int) -> tuple[np.ndarray, float, float]:
    """Reduce la imagen sin deformarla hasta que su lado mayor mida como mucho lado_maximo.

    Devuelve también los factores que pasan coordenadas de la imagen reducida a la original.
    """
    alto, ancho = imagen.shape[:2]
    if max(alto, ancho) <= lado_maximo:
        return imagen, 1.0, 1.0
    escala = lado_maximo / max(alto, ancho)
    nuevo_ancho = max(1, round(ancho * escala))
    nuevo_alto = max(1, round(alto * escala))
    reducida = cv2.resize(imagen, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_AREA)
    return reducida, ancho / nuevo_ancho, alto / nuevo_alto


def codificar_jpeg(imagen: np.ndarray) -> bytes:
    ok, datos = cv2.imencode(".jpg", imagen)
    if not ok:
        raise ValueError("No se pudo codificar la imagen")
    return datos.tobytes()


def a_original(
    caja: list[float], factor_x: float, factor_y: float, ancho: int, alto: int
) -> tuple[float, float, float, float]:
    """Pasa una caja de la imagen reducida a la original, ordenada y dentro de sus bordes."""
    x1, x2 = sorted((caja[0] * factor_x, caja[2] * factor_x))
    y1, y2 = sorted((caja[1] * factor_y, caja[3] * factor_y))
    return (
        min(max(x1, 0.0), ancho),
        min(max(y1, 0.0), alto),
        min(max(x2, 0.0), ancho),
        min(max(y2, 0.0), alto),
    )


def recortar(imagen: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> bytes:
    """JPEG de la zona de la caja, reducido a 256 píxeles de lado como máximo."""
    alto, ancho = imagen.shape[:2]
    x1 = min(max(x1, 0), ancho - 1)
    y1 = min(max(y1, 0), alto - 1)
    x2 = min(max(x2, x1 + 1), ancho)
    y2 = min(max(y2, y1 + 1), alto)
    zona, _, _ = reducir(imagen[y1:y2, x1:x2], LADO_RECORTE)
    return codificar_jpeg(zona)


def _dimensiones_png(datos: bytes) -> tuple[int, int] | None:
    if len(datos) >= 24 and datos[12:16] == b"IHDR":
        return int.from_bytes(datos[16:20], "big"), int.from_bytes(datos[20:24], "big")
    return None


def _dimensiones_jpeg(datos: bytes) -> tuple[int, int] | None:
    """Lee ancho y alto del marcador SOF del JPEG sin decodificar la imagen."""
    i = 2
    while i + 9 <= len(datos):
        if datos[i] != 0xFF:
            return None
        marcador = datos[i + 1]
        if marcador == 0xFF:  # byte de relleno
            i += 1
            continue
        if marcador == 0x01 or 0xD0 <= marcador <= 0xD9:  # marcadores sin longitud
            i += 2
            continue
        if marcador == 0xDA:  # empiezan los datos de la imagen sin haber visto el SOF
            return None
        if 0xC0 <= marcador <= 0xCF and marcador not in (0xC4, 0xC8, 0xCC):
            alto = int.from_bytes(datos[i + 5:i + 7], "big")
            ancho = int.from_bytes(datos[i + 7:i + 9], "big")
            return ancho, alto
        i += 2 + int.from_bytes(datos[i + 2:i + 4], "big")
    return None


def decodificar_fotograma(datos: bytes) -> np.ndarray:
    """Decodifica un fotograma del modo en vivo: solo JPEG o PNG de 1920 × 1920 como máximo.

    El tipo se comprueba por los primeros bytes y el tamaño por la cabecera, antes de
    decodificar, y otra vez sobre la imagen decodificada.
    """
    if datos.startswith(FIRMA_PNG):
        dimensiones = _dimensiones_png(datos)
    elif datos.startswith(FIRMA_JPEG):
        dimensiones = _dimensiones_jpeg(datos)
    else:
        raise ImagenNoAdmitida
    if dimensiones and max(dimensiones) > LADO_MAXIMO_EN_VIVO:
        raise ImagenDemasiadoGrande
    try:
        imagen = cv2.imdecode(np.frombuffer(datos, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        raise ImagenDemasiadoGrande from None
    if imagen is None:
        raise ImagenNoAdmitida
    if max(imagen.shape[:2]) > LADO_MAXIMO_EN_VIVO:
        raise ImagenDemasiadoGrande
    return imagen
