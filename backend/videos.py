"""Vídeos: comprobación del tipo real, la duración y la resolución, y extracción de fotogramas."""

import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import imagenes  # noqa: F401  fija el límite de píxeles de OpenCV antes de importar cv2
import cv2  # noqa: E402
import numpy as np  # noqa: E402

EXTENSIONES = (".mp4", ".mov", ".webm", ".avi")
DURACION_MAXIMA_S = 120
LADO_LARGO_MAXIMO = 3840
LADO_CORTO_MAXIMO = 2160  # se admiten vídeos horizontales y verticales de hasta 3840 × 2160

DEMASIADO_LARGO = "El vídeo no puede durar más de 2 minutos."
DEMASIADO_GRANDE = "El vídeo no puede superar 3840 × 2160 píxeles."


class VideoNoAdmitido(Exception):
    """El archivo no es un MP4, MOV, WEBM o AVI que OpenCV pueda leer."""


class VideoFueraDeLimites(Exception):
    """El vídeo dura demasiado o tiene demasiada resolución."""


@dataclass(frozen=True)
class InfoVideo:
    fps: float
    fotogramas: int
    duracion_s: float
    ancho: int
    alto: int


def tipo_real(cabecera: bytes) -> str | None:
    """Familia del contenedor según sus primeros bytes, sin fiarse de la extensión."""
    cajas_iso = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip")
    if len(cabecera) >= 12 and cabecera[4:8] in cajas_iso:
        return "mp4_mov"  # MP4 y MOV comparten la misma estructura de cajas
    if cabecera.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in cabecera:
        return "webm"  # un MKV usa la misma cabecera pero declara matroska
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"AVI ":
        return "avi"
    return None


def inspeccionar(ruta: Path) -> InfoVideo:
    """Comprueba que OpenCV lee el vídeo y que está dentro de los límites de duración y tamaño."""
    with open(ruta, "rb") as archivo:
        cabecera = archivo.read(64)
    if tipo_real(cabecera) is None:
        raise VideoNoAdmitido
    captura = cv2.VideoCapture(str(ruta))
    try:
        if not captura.isOpened():
            raise VideoNoAdmitido
        ok, fotograma = captura.read()
        if not ok or fotograma is None:
            raise VideoNoAdmitido
        alto, ancho = fotograma.shape[:2]
        if max(ancho, alto) > LADO_LARGO_MAXIMO or min(ancho, alto) > LADO_CORTO_MAXIMO:
            raise VideoFueraDeLimites(DEMASIADO_GRANDE)
        fps = captura.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise VideoNoAdmitido  # sin fps no se puede situar cada fotograma en el tiempo
        total = captura.get(cv2.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(total) or total < 1:
            total = _contar(captura, fps)
        duracion = round(total / fps, 3)
        if duracion > DURACION_MAXIMA_S:
            raise VideoFueraDeLimites(DEMASIADO_LARGO)
        return InfoVideo(fps=fps, fotogramas=int(total), duracion_s=duracion, ancho=ancho, alto=alto)
    finally:
        captura.release()


def _contar(captura: cv2.VideoCapture, fps: float) -> int:
    """Cuenta los fotogramas cuando el contenedor no lo dice, parando al pasar del máximo."""
    total = 1  # el primero ya se ha leído
    while captura.grab():
        total += 1
        if total / fps > DURACION_MAXIMA_S:
            raise VideoFueraDeLimites(DEMASIADO_LARGO)
    return total


def numero_de_muestras(duracion_s: float, intervalo_s: float) -> int:
    """Fotogramas que se analizan: uno cada intervalo_s segundos, empezando en el segundo 0."""
    return max(1, math.ceil(round(duracion_s / intervalo_s, 6)))


def muestrear(
    ruta: Path, info: InfoVideo, intervalo_s: float
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Recorre el vídeo y devuelve, en orden, (número de muestra, segundo, fotograma).

    Lee el vídeo de principio a fin y solo decodifica entero el fotograma de cada muestra.
    Si el vídeo se acaba antes de lo que decía su cabecera, se detiene ahí.
    """
    captura = cv2.VideoCapture(str(ruta))
    try:
        indice = -1
        fotograma = None
        for k in range(numero_de_muestras(info.duracion_s, intervalo_s)):
            objetivo = min(round(k * intervalo_s * info.fps), info.fotogramas - 1)
            while indice < objetivo - 1:
                if not captura.grab():
                    return
                indice += 1
            if indice < objetivo:
                ok, fotograma = captura.read()
                if not ok:
                    return
                indice += 1
            # Si el vídeo tiene menos fotogramas que muestras, se repite el último leído
            yield k, round(objetivo / info.fps, 3), fotograma
    finally:
        captura.release()
