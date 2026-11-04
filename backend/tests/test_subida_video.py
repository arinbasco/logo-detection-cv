"""Validación de la subida de vídeo: tamaño, formato real, duración, resolución y análisis único."""

import asyncio
import threading

import pytest

from rutas import FORMATO_VIDEO
from seguridad import ANALISIS_EN_CURSO, MARGEN_FORMULARIO, MAX_BYTES_VIDEO, VIDEO_GRANDE, LimiteCuerpo


def test_texto_renombrado_a_mp4_recibe_415(cliente, subir, carpeta_temporal):
    respuesta = subir(cliente, b"esto es un archivo de texto\n" * 200, nombre="falso.mp4")
    assert respuesta.status_code == 415
    assert respuesta.json() == {"detail": FORMATO_VIDEO}
    assert list(carpeta_temporal.iterdir()) == []


@pytest.mark.parametrize("nombre", ["video.mkv", "video.gif", "video"])
def test_extension_no_admitida_recibe_415(cliente, crear_video, subir, nombre):
    assert subir(cliente, crear_video(segundos=1), nombre=nombre).status_code == 415


def test_mkv_renombrado_a_webm_recibe_415(cliente, crear_video, subir):
    mkv = crear_video(segundos=1, extension=".mkv", fourcc="MJPG")
    assert subir(cliente, mkv, nombre="video.webm").status_code == 415


@pytest.mark.parametrize("extension, fourcc", [(".webm", "VP80"), (".avi", "MJPG"), (".mov", "mp4v"), (".MP4", "mp4v")])
def test_formatos_admitidos(cliente, crear_video, subir, esperar_analisis, extension, fourcc):
    datos = crear_video(segundos=2, extension=extension.lower(), fourcc=fourcc)
    respuesta = subir(cliente, datos, nombre=f"video{extension}")
    assert respuesta.status_code == 202
    assert esperar_analisis(cliente, respuesta.json()["id"])["estado"] == "completado"


def test_video_de_mas_de_2_minutos_recibe_422(cliente, crear_video, subir, carpeta_temporal):
    respuesta = subir(cliente, crear_video(segundos=121, fps=2, ancho=64, alto=48))
    assert respuesta.status_code == 422
    assert "2 minutos" in respuesta.json()["detail"]
    assert list(carpeta_temporal.iterdir()) == []


def test_resolucion_maxima_en_horizontal_y_vertical(cliente, crear_video, subir, esperar_analisis):
    vertical = subir(cliente, crear_video(segundos=1, fps=2, ancho=2160, alto=3840))
    assert vertical.status_code == 202
    esperar_analisis(cliente, vertical.json()["id"])
    # El lado largo pasa de 3840, o el corto de 2160
    for ancho, alto in ((3842, 100), (2200, 2200)):
        respuesta = subir(cliente, crear_video(segundos=1, fps=2, ancho=ancho, alto=alto))
        assert respuesta.status_code == 422
        assert "3840 × 2160" in respuesta.json()["detail"]


@pytest.mark.parametrize("campos", [
    {"intervalo_s": 0.4}, {"intervalo_s": 5.1}, {"intervalo_s": "nan"},
    {"umbral": 0.04}, {"umbral": 0.96}, {"umbral": "abc"},
])
def test_parametros_fuera_de_rango_reciben_422_generico(cliente, crear_video, subir, campos):
    respuesta = subir(cliente, crear_video(segundos=1), **campos)
    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "Parámetros no válidos o fuera de rango."}


def test_segundo_analisis_en_curso_recibe_429(cliente, api_modelo, crear_video, subir, esperar_analisis):
    api_modelo.permisos = threading.Semaphore(0)
    primero = subir(cliente, crear_video(segundos=2))
    assert primero.status_code == 202
    segundo = subir(cliente, crear_video(segundos=2))
    assert segundo.status_code == 429
    assert segundo.json() == {"detail": ANALISIS_EN_CURSO}
    api_modelo.permisos.release(2)
    assert esperar_analisis(cliente, primero.json()["id"])["estado"] == "completado"
    # Al terminar se libera el hueco
    api_modelo.permisos = None
    assert subir(cliente, crear_video(segundos=1)).status_code == 202


def test_un_rechazo_tambien_libera_el_hueco(cliente, crear_video, subir):
    assert subir(cliente, b"texto", nombre="falso.mp4").status_code == 415
    assert subir(cliente, crear_video(segundos=1)).status_code == 202


def test_video_de_mas_de_100_mb_recibe_413(cliente, subir, carpeta_temporal):
    # Justo por encima del máximo: lo corta la copia por trozos
    respuesta = subir(cliente, b"\x00" * (MAX_BYTES_VIDEO + 1))
    assert respuesta.status_code == 413
    assert respuesta.json() == {"detail": VIDEO_GRANDE}
    # Muy por encima: lo corta el middleware al ver la longitud, sin leer el cuerpo
    respuesta = subir(cliente, b"\x00" * (MAX_BYTES_VIDEO + MARGEN_FORMULARIO + 1))
    assert respuesta.status_code == 413
    assert list(carpeta_temporal.iterdir()) == []


def test_el_corte_llega_antes_de_recibir_el_video_entero():
    """Sin cabecera de longitud, el middleware corta en cuanto pasa del máximo mientras llega."""
    trozo = b"\x00" * (1024 * 1024)
    pedidos = 0
    leidos_por_la_app = 0

    async def recibir():
        nonlocal pedidos
        pedidos += 1
        return {"type": "http.request", "body": trozo, "more_body": pedidos < 150}  # 150 MB

    async def app_interna(scope, receive, send):
        nonlocal leidos_por_la_app
        while True:
            mensaje = await receive()
            leidos_por_la_app += len(mensaje["body"])
            if not mensaje.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 202, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    enviados = []

    async def enviar(mensaje):
        enviados.append(mensaje)

    middleware = LimiteCuerpo(app_interna, analisis_en_curso=lambda: False)
    scope = {"type": "http", "method": "POST", "path": "/analisis", "headers": []}
    asyncio.run(middleware(scope, recibir, enviar))
    assert enviados[0]["status"] == 413
    assert pedidos == 101  # se detiene en el primer trozo que pasa de 100 MB, sin pedir los 150
    assert leidos_por_la_app == 100 * len(trozo)  # la app nunca recibe el trozo que excede
