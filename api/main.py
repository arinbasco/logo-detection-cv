"""API de detección de logos con YOLO26n exportado a ONNX.

Recibe una imagen y devuelve las marcas detectadas con su confianza y su caja.
Solo usa onnxruntime, numpy y OpenCV para que quepa en un servidor con poca memoria.
"""

import ast
import os
import secrets
from pathlib import Path

# OpenCV se niega a decodificar imágenes de más de 4096 x 4096 píxeles.
# Evita que una imagen pequeña en bytes pero enorme en píxeles agote la memoria.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(4096 * 4096))

import cv2  # noqa: E402
import numpy as np
import onnxruntime as ort
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.security import APIKeyHeader

RUTA_MODELO = Path(os.getenv("RUTA_MODELO", Path(__file__).parent / "best.onnx"))
TAMANO = 640          # tamaño de entrada con el que se entrenó y exportó el modelo
IOU_NMS = 0.7         # mismo umbral de NMS que usa Ultralytics por defecto al predecir
MAX_BYTES = 5 * 1024 * 1024      # tamaño máximo del archivo recibido (5 MB)
MAX_PIXELES = 4096 * 4096        # tamaño máximo de la imagen decodificada

# La clave se lee de una variable de entorno, nunca se escribe en el código
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("Falta la variable de entorno API_KEY")
MOSTRAR_DOCS = os.getenv("MOSTRAR_DOCS", "1") == "1"
cabecera_clave = APIKeyHeader(name="X-API-Key", auto_error=False)


def comprobar_clave(clave: str | None = Depends(cabecera_clave)) -> None:
    """Rechaza la petición si no trae la clave correcta en la cabecera X-API-Key."""
    if clave is None or not secrets.compare_digest(clave, API_KEY):
        raise HTTPException(status_code=401, detail="Clave de API ausente o incorrecta")

# El modelo se carga una sola vez, al arrancar el servidor
sesion = ort.InferenceSession(str(RUTA_MODELO), providers=["CPUExecutionProvider"])
ENTRADA = sesion.get_inputs()[0].name
# Ultralytics guarda los nombres de las clases en los metadatos del ONNX
NOMBRES = ast.literal_eval(sesion.get_modelmeta().custom_metadata_map["names"])

app = FastAPI(
    title="API de detección de logos",
    version="1.1",
    docs_url="/docs" if MOSTRAR_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if MOSTRAR_DOCS else None,
)


def letterbox(imagen: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Redimensiona sin deformar y rellena con gris hasta 640x640, como hace Ultralytics."""
    alto, ancho = imagen.shape[:2]
    escala = min(TAMANO / alto, TAMANO / ancho)
    nuevo_ancho, nuevo_alto = round(ancho * escala), round(alto * escala)
    redimensionada = cv2.resize(imagen, (nuevo_ancho, nuevo_alto), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (TAMANO - nuevo_ancho) // 2, (TAMANO - nuevo_alto) // 2
    lienzo = np.full((TAMANO, TAMANO, 3), 114, dtype=np.uint8)
    lienzo[pad_y:pad_y + nuevo_alto, pad_x:pad_x + nuevo_ancho] = redimensionada
    return lienzo, escala, (pad_x, pad_y)


def detectar(imagen_bgr: np.ndarray, conf: float) -> list[dict]:
    """Ejecuta el modelo sobre una imagen BGR y devuelve las detecciones en píxeles originales."""
    alto, ancho = imagen_bgr.shape[:2]
    lienzo, escala, (pad_x, pad_y) = letterbox(imagen_bgr)

    # BGR a RGB, de HWC a CHW, valores entre 0 y 1, y dimensión de lote
    entrada = lienzo[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    salida = sesion.run(None, {ENTRADA: entrada})[0][0]   # forma (4 + clases, 8400)
    salida = salida.T                                     # forma (8400, 4 + clases)

    puntuaciones = salida[:, 4:]
    clases = puntuaciones.argmax(axis=1)
    confianzas = puntuaciones[np.arange(len(clases)), clases]
    mantener = confianzas >= conf
    if not mantener.any():
        return []
    cajas, clases, confianzas = salida[mantener, :4], clases[mantener], confianzas[mantener]

    # De centro, ancho y alto a esquina superior izquierda, ancho y alto (formato de NMSBoxes)
    xywh = cajas.copy()
    xywh[:, 0] -= xywh[:, 2] / 2
    xywh[:, 1] -= xywh[:, 3] / 2

    # NMS por clase, desplazando cada clase para que sus cajas no se mezclen con las de otras
    desplazadas = xywh.copy()
    desplazadas[:, :2] += clases[:, None] * 4096
    indices = cv2.dnn.NMSBoxes(desplazadas.tolist(), confianzas.tolist(), conf, IOU_NMS)
    indices = np.array(indices).flatten()

    detecciones = []
    for i in indices:
        x, y, w, h = xywh[i]
        # Deshacer el relleno y la escala para volver a la imagen original
        x1 = float(np.clip((x - pad_x) / escala, 0, ancho))
        y1 = float(np.clip((y - pad_y) / escala, 0, alto))
        x2 = float(np.clip((x + w - pad_x) / escala, 0, ancho))
        y2 = float(np.clip((y + h - pad_y) / escala, 0, alto))
        detecciones.append({
            "marca": NOMBRES[int(clases[i])],
            "confianza": round(float(confianzas[i]), 4),
            "caja": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
        })
    return sorted(detecciones, key=lambda d: d["confianza"], reverse=True)


@app.get("/")
def estado() -> dict:
    """Comprueba que la API está viva y muestra las marcas que reconoce."""
    return {"estado": "ok", "modelo": RUTA_MODELO.name, "marcas": list(NOMBRES.values())}


@app.post("/predict", dependencies=[Depends(comprobar_clave)])
async def predecir(
    imagen: UploadFile = File(..., description="Imagen JPG o PNG"),
    conf: float = Query(0.25, ge=0.0, le=1.0, description="Umbral de confianza"),
) -> dict:
    """Recibe una imagen y devuelve las marcas detectadas. Requiere la cabecera X-API-Key."""
    contenido = await imagen.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="La imagen supera los 5 MB")
    try:
        imagen_bgr = cv2.imdecode(np.frombuffer(contenido, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        raise HTTPException(status_code=413, detail="La imagen es demasiado grande") from None
    if imagen_bgr is None:
        raise HTTPException(status_code=400, detail="No se pudo leer la imagen")
    alto, ancho = imagen_bgr.shape[:2]
    if alto * ancho > MAX_PIXELES:
        raise HTTPException(status_code=413, detail="La imagen es demasiado grande")
    return {
        "ancho": ancho,
        "alto": alto,
        "conf": conf,
        "detecciones": detectar(imagen_bgr, conf),
    }