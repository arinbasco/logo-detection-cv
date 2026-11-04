"""La clave de la API del modelo se usa en cada llamada pero nunca sale en respuestas ni registros."""

import logging

import cv2
import numpy as np

from conftest import CLAVE_FALSA

NIKE = {"marca": "Nike", "confianza": 0.9, "caja": [10, 10, 60, 50]}


def test_la_clave_no_aparece_en_respuestas_ni_en_registros(
    crear_cliente, api_modelo, crear_video, subir, esperar_analisis, caplog,
):
    caplog.set_level(logging.DEBUG)  # el nivel más detallado, incluidas las librerías
    cliente = crear_cliente(lanzar_errores=False)
    api_modelo.guion = ["error", [NIKE], "sin_respuesta", "sin_respuesta", "formato_raro", [NIKE]]

    respuestas = [cliente.get("/salud"), cliente.get("/config"), cliente.get("/marcas")]
    creado = subir(cliente, crear_video(segundos=3))
    respuestas.append(creado)
    analisis_id = creado.json()["id"]
    esperar_analisis(cliente, analisis_id)
    for ruta in ("", "/informe", "/detecciones"):
        respuestas.append(cliente.get(f"/analisis/{analisis_id}{ruta}"))

    sesion = cliente.post("/en-vivo/sesion", data={"nombre_video": "v.mp4", "duracion_s": "10"})
    respuestas.append(sesion)
    api_modelo.por_defecto = "error"
    fotograma = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))[1].tobytes()
    respuestas.append(cliente.post(
        "/en-vivo/fotograma", files={"imagen": ("f.jpg", fotograma, "image/jpeg")},
        data={"sesion_id": sesion.json()["id"], "t_s": "1"},
    ))

    def fallar():
        raise RuntimeError("fallo interno")

    cliente.app.state.contexto.cliente.media.valor = fallar
    respuestas.append(cliente.get("/config"))

    assert [r.status_code for r in respuestas] == [200, 200, 200, 202, 200, 200, 200, 201, 502, 500]
    assert any(r.levelno >= logging.WARNING for r in caplog.records), "debería haber avisos que revisar"
    assert CLAVE_FALSA not in caplog.text
    for respuesta in respuestas:
        assert CLAVE_FALSA not in respuesta.text
        assert CLAVE_FALSA not in str(respuesta.headers)
    # La clave sí viaja en la cabecera X-API-Key de cada llamada a la API del modelo
    assert set(api_modelo.claves_recibidas) == {CLAVE_FALSA}
