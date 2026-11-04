"""Flujo del modo informe: análisis en segundo plano, informe, detecciones y recortes."""

import threading
import uuid

import cv2
import numpy as np

from modelos import Analisis
from procesamiento import ERROR_SIN_RESPUESTA
from rutas import SIN_RESULTADOS, SIN_TERMINAR

NIKE = {"marca": "Nike", "confianza": 0.9, "caja": [10, 10, 60, 50]}
PUMA = {"marca": "Puma", "confianza": 0.95, "caja": [80, 20, 120, 60]}


def _fila(cliente, analisis_id: str) -> Analisis:
    with cliente.app.state.contexto.sesiones() as sesion:
        return sesion.get(Analisis, uuid.UUID(analisis_id))


def test_video_de_10_segundos_completo(cliente, api_modelo, crear_video, subir, esperar_analisis, carpeta_temporal):
    api_modelo.por_defecto = [NIKE]
    api_modelo.permisos = threading.Semaphore(0)
    creado = subir(cliente, crear_video(segundos=10, fps=10), intervalo_s=1)
    assert creado.status_code == 202
    assert set(creado.json()) == {"id", "estado", "tiempo_estimado_s"}
    assert creado.json()["estado"] == "en_cola"
    analisis_id = creado.json()["id"]
    # Mientras se analiza, el vídeo existe en la carpeta temporal con un nombre UUID
    temporales = list(carpeta_temporal.iterdir())
    assert len(temporales) == 1
    assert uuid.UUID(temporales[0].stem) and temporales[0].suffix == ".mp4"
    api_modelo.permisos.release(10)

    estado = esperar_analisis(cliente, analisis_id)
    assert estado["estado"] == "completado"
    assert estado["progreso"] == 1
    assert estado["tiempo_restante_s"] == 0
    assert estado["nombre_video"] == "video.mp4"
    assert api_modelo.llamadas_predict == 10
    assert _fila(cliente, analisis_id).fotogramas_analizados == 10
    assert list(carpeta_temporal.iterdir()) == []

    detecciones = cliente.get(f"/analisis/{analisis_id}/detecciones").json()
    assert [d["t_s"] for d in detecciones] == [float(s) for s in range(10)]
    informe = cliente.get(f"/analisis/{analisis_id}/informe").json()
    assert informe["marcas"] == [{
        "marca": "Nike", "segundos": 10.0, "porcentaje": 100.0, "detecciones": 10, "confianza_media": 0.9,
    }]


def test_varias_cajas_de_una_marca_suman_una_vez_por_fotograma(cliente, api_modelo, crear_video, subir, esperar_analisis):
    otra_nike = {"marca": "Nike", "confianza": 0.8, "caja": [70, 10, 110, 50]}
    api_modelo.por_defecto = [NIKE, otra_nike, PUMA]
    analisis_id = subir(cliente, crear_video(segundos=5)).json()["id"]
    assert esperar_analisis(cliente, analisis_id)["estado"] == "completado"
    marcas = {m["marca"]: m for m in cliente.get(f"/analisis/{analisis_id}/informe").json()["marcas"]}
    assert marcas["Nike"]["segundos"] == 5.0
    assert marcas["Nike"]["detecciones"] == 10
    assert marcas["Nike"]["confianza_media"] == 0.85
    assert marcas["Puma"]["segundos"] == 5.0


def test_fotogramas_a_la_api_con_640_px_como_maximo(cliente, api_modelo, crear_video, subir, esperar_analisis):
    api_modelo.por_defecto = [{"marca": "Nike", "confianza": 0.9, "caja": [100, 50, 200, 150]}]
    analisis_id = subir(cliente, crear_video(segundos=2, fps=5, ancho=1280, alto=720)).json()["id"]
    assert esperar_analisis(cliente, analisis_id)["estado"] == "completado"
    assert api_modelo.imagenes_recibidas == [(640, 360), (640, 360)]
    # Las cajas se guardan en píxeles del fotograma original
    detecciones = cliente.get(f"/analisis/{analisis_id}/detecciones").json()
    assert detecciones[0]["caja"] == [200, 100, 400, 300]


def test_recorte_es_un_jpeg_valido(cliente, api_modelo, crear_video, subir, esperar_analisis):
    api_modelo.por_defecto = [{"marca": "Nike", "confianza": 0.9, "caja": [0, 0, 600, 300]}]
    analisis_id = subir(cliente, crear_video(segundos=1, fps=5, ancho=1280, alto=720)).json()["id"]
    esperar_analisis(cliente, analisis_id)
    deteccion = cliente.get(f"/analisis/{analisis_id}/detecciones").json()[0]
    respuesta = cliente.get(f"/recortes/{deteccion['recorte_id']}")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.content.startswith(b"\xff\xd8\xff")
    imagen = cv2.imdecode(np.frombuffer(respuesta.content, np.uint8), cv2.IMREAD_COLOR)
    assert imagen is not None
    assert max(imagen.shape[:2]) == 256


def test_filtro_por_marca_y_orden_por_tiempo(cliente, api_modelo, crear_video, subir, esperar_analisis):
    api_modelo.guion = [[NIKE], [PUMA, NIKE], [PUMA]]
    analisis_id = subir(cliente, crear_video(segundos=3)).json()["id"]
    esperar_analisis(cliente, analisis_id)
    todas = cliente.get(f"/analisis/{analisis_id}/detecciones").json()
    assert [(d["t_s"], d["marca"]) for d in todas] == [(0.0, "Nike"), (1.0, "Puma"), (1.0, "Nike"), (2.0, "Puma")]
    assert set(todas[0]) == {"id", "t_s", "marca", "confianza", "caja", "recorte_id"}
    pumas = cliente.get(f"/analisis/{analisis_id}/detecciones", params={"marca": "Puma"}).json()
    assert [d["t_s"] for d in pumas] == [1.0, 2.0]


def test_tiempo_estimado_y_tiempo_restante_que_baja(cliente, api_modelo, crear_video, subir, esperar_progreso):
    api_modelo.por_defecto = [NIKE]
    api_modelo.permisos = threading.Semaphore(0)
    creado = subir(cliente, crear_video(segundos=4))
    # Sin medidas todavía, la media de partida es 3,5 s por fotograma: 4 × 3,5
    assert creado.json()["tiempo_estimado_s"] == 14.0
    analisis_id = creado.json()["id"]
    # Fija la media para que el tiempo restante dependa solo de los fotogramas pendientes
    cliente.app.state.contexto.cliente.media.valor = lambda: 2.0
    restantes = [cliente.get(f"/analisis/{analisis_id}").json()["tiempo_restante_s"]]
    for procesados in range(1, 5):
        api_modelo.permisos.release()
        esperar_progreso(cliente, analisis_id, procesados, total=4)
        restantes.append(cliente.get(f"/analisis/{analisis_id}").json()["tiempo_restante_s"])
    assert restantes == [8.0, 6.0, 4.0, 2.0, 0.0]


def test_la_media_se_actualiza_con_las_llamadas_reales(cliente, api_modelo, crear_video, subir, esperar_analisis):
    api_modelo.por_defecto = [NIKE]
    esperar_analisis(cliente, subir(cliente, crear_video(segundos=3)).json()["id"])
    # La API simulada responde en milisegundos, así que la media baja de los 3,5 s iniciales
    assert cliente.get("/config").json()["segundos_por_fotograma"] < 3.5


def test_campos_del_estado_del_analisis(cliente, api_modelo, crear_video, subir, esperar_analisis):
    analisis_id = subir(cliente, crear_video(segundos=2), intervalo_s=0.5, umbral=0.6).json()["id"]
    estado = esperar_analisis(cliente, analisis_id)
    assert set(estado) == {
        "id", "nombre_video", "modo", "estado", "progreso", "duracion_s", "fps", "intervalo_s", "umbral",
        "creado", "error", "tiempo_restante_s",
    }
    assert estado["modo"] == "informe"
    assert (estado["duracion_s"], estado["fps"], estado["intervalo_s"], estado["umbral"]) == (2.0, 10.0, 0.5, 0.6)
    assert estado["error"] is None
    assert api_modelo.llamadas_predict == 4
    assert set(api_modelo.umbrales_recibidos) == {0.6}


def test_si_la_api_del_modelo_no_responde_el_analisis_falla_sin_colgarse(
    cliente, api_modelo, crear_video, subir, esperar_analisis, carpeta_temporal,
):
    api_modelo.por_defecto = "sin_respuesta"
    analisis_id = subir(cliente, crear_video(segundos=10)).json()["id"]
    estado = esperar_analisis(cliente, analisis_id)
    assert estado["estado"] == "fallido"
    assert estado["error"] == ERROR_SIN_RESPUESTA
    for detalle in ("Timeout", "httpx", "http://", "api-modelo", "Traceback", "simulado"):
        assert detalle not in estado["error"]
    # 3 fotogramas seguidos sin respuesta, con un reintento cada uno, y se rinde
    assert api_modelo.llamadas_predict == 6
    assert list(carpeta_temporal.iterdir()) == []
    assert cliente.get(f"/analisis/{analisis_id}/informe").json() == {"detail": SIN_RESULTADOS}


def test_fallos_sueltos_dejan_fotogramas_sin_analizar(cliente, api_modelo, crear_video, subir, esperar_analisis):
    api_modelo.guion = [
        "sin_respuesta", "sin_respuesta",  # fotograma 0: falla dos veces y queda sin analizar
        [NIKE],                            # fotograma 1
        "error", [NIKE],                   # fotograma 2: falla y el reintento funciona
        "formato_raro", "formato_raro",    # fotograma 3: respuesta inválida dos veces
        [NIKE],                            # fotograma 4
    ]
    analisis_id = subir(cliente, crear_video(segundos=5)).json()["id"]
    assert esperar_analisis(cliente, analisis_id)["estado"] == "completado"
    assert _fila(cliente, analisis_id).fotogramas_analizados == 3
    assert api_modelo.llamadas_predict == 8
    detecciones = cliente.get(f"/analisis/{analisis_id}/detecciones").json()
    assert [d["t_s"] for d in detecciones] == [1.0, 2.0, 4.0]


def test_informe_y_detecciones_responden_409_mientras_no_termina(cliente, api_modelo, crear_video, subir):
    api_modelo.permisos = threading.Semaphore(0)
    analisis_id = subir(cliente, crear_video(segundos=2)).json()["id"]
    for ruta in ("informe", "detecciones"):
        respuesta = cliente.get(f"/analisis/{analisis_id}/{ruta}")
        assert respuesta.status_code == 409
        assert respuesta.json() == {"detail": SIN_TERMINAR}
    api_modelo.permisos.release(2)


def test_mismo_404_para_id_inexistente_y_mal_formado(cliente):
    for plantilla in ("/analisis/{}", "/analisis/{}/informe", "/analisis/{}/detecciones", "/recortes/{}"):
        inexistente = cliente.get(plantilla.format(uuid.uuid4()))
        mal_formado = cliente.get(plantilla.format("no-es-un-uuid"))
        assert inexistente.status_code == mal_formado.status_code == 404
        assert inexistente.json() == mal_formado.json() == {"detail": "No encontrado."}
