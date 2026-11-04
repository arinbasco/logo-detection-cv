"""Sesiones del modo en vivo: apertura, fotogramas guardados, cierre, informe y estados."""

import uuid

import pytest
from sqlalchemy import select

from conftest import abrir_sesion, crear_imagen, enviar_fotograma
from modelos import Analisis, Fotograma
from rutas import NO_ENCONTRADO, SIN_RESULTADOS, SIN_TERMINAR
from rutas_en_vivo import ERROR_SIN_FOTOGRAMAS, SESION_FALLIDA, SESION_TERMINADA
from videos import DEMASIADO_LARGO

NIKE = {"marca": "Nike", "confianza": 0.9, "caja": [10, 10, 60, 50]}
PUMA = {"marca": "Puma", "confianza": 0.8, "caja": [80, 20, 120, 60]}


def _fila(cliente, analisis_id: str) -> Analisis:
    with cliente.app.state.contexto.sesiones() as sesion:
        return sesion.get(Analisis, uuid.UUID(analisis_id))


def _segundos_guardados(cliente, analisis_id: str) -> list[float]:
    with cliente.app.state.contexto.sesiones() as sesion:
        consulta = select(Fotograma.t_s).where(Fotograma.analisis_id == uuid.UUID(analisis_id)).order_by(Fotograma.t_s)
        return list(sesion.scalars(consulta))


def _cerrar(cliente, sesion_id: str):
    return cliente.post(f"/en-vivo/sesion/{sesion_id}/fin")


def test_abrir_una_sesion(cliente):
    respuesta = abrir_sesion(cliente, nombre_video="partido.mp4", duracion_s=20, umbral=0.6)
    assert respuesta.status_code == 201
    assert set(respuesta.json()) == {"id"}
    estado = cliente.get(f"/analisis/{respuesta.json()['id']}").json()
    assert {clave: valor for clave, valor in estado.items() if clave not in ("id", "creado")} == {
        "nombre_video": "partido.mp4", "modo": "en_vivo", "estado": "procesando", "progreso": 0.0,
        "duracion_s": 20.0, "fps": None, "intervalo_s": None, "umbral": 0.6, "error": None,
        "tiempo_restante_s": 0.0,
    }


def test_sesion_completa_con_informe_detecciones_y_recortes(cliente, api_modelo):
    api_modelo.guion = [[NIKE], [], [NIKE, PUMA], []]
    sesion_id = abrir_sesion(cliente, duracion_s=20).json()["id"]
    for t_s in (0, 2, 4, 15):
        assert enviar_fotograma(cliente, sesion_id, crear_imagen(1280, 720), t_s=t_s).status_code == 200
    # Mientras está abierta, el progreso es el segundo más alto entre la duración
    abierta = cliente.get(f"/analisis/{sesion_id}").json()
    assert (abierta["estado"], abierta["progreso"], abierta["tiempo_restante_s"]) == ("procesando", 0.75, 0.0)
    for ruta in ("informe", "detecciones"):
        assert cliente.get(f"/analisis/{sesion_id}/{ruta}").json() == {"detail": SIN_TERMINAR}

    cierre = _cerrar(cliente, sesion_id)
    assert cierre.status_code == 200
    assert (cierre.json()["estado"], cierre.json()["progreso"], cierre.json()["modo"]) == ("completado", 1.0, "en_vivo")
    assert cierre.json() == cliente.get(f"/analisis/{sesion_id}").json()
    # Se guardan también los fotogramas sin detecciones
    assert _fila(cliente, sesion_id).fotogramas_analizados == 4
    assert _segundos_guardados(cliente, sesion_id) == [0.0, 2.0, 4.0, 15.0]

    informe = cliente.get(f"/analisis/{sesion_id}/informe").json()
    # Los fotogramas pesan 2, 2, 5 (con el tope) y 5 s: Nike está en 0 y 4, Puma en 4
    assert informe["marcas"] == [
        {"marca": "Nike", "segundos": 7.0, "porcentaje": 35.0, "detecciones": 2, "confianza_media": 0.9},
        {"marca": "Puma", "segundos": 5.0, "porcentaje": 25.0, "detecciones": 1, "confianza_media": 0.8},
    ]
    detecciones = cliente.get(f"/analisis/{sesion_id}/detecciones").json()
    assert [(d["t_s"], d["marca"]) for d in detecciones] == [(0.0, "Nike"), (4.0, "Nike"), (4.0, "Puma")]
    # Las cajas se guardan en píxeles de la imagen que envió el front, no de la reducida
    assert detecciones[0]["caja"] == [20, 20, 120, 100]
    recorte = cliente.get(f"/recortes/{detecciones[0]['recorte_id']}")
    assert recorte.status_code == 200
    assert recorte.headers["content-type"] == "image/jpeg"
    assert recorte.content.startswith(b"\xff\xd8\xff")


def test_un_fotograma_sin_respuesta_del_modelo_no_cuenta(cliente, api_modelo):
    api_modelo.guion = ["error", "error", [NIKE]]  # el primero falla también al reintentar
    sesion_id = abrir_sesion(cliente).json()["id"]
    assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48), t_s=1).status_code == 502
    assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48), t_s=3).status_code == 200
    assert _cerrar(cliente, sesion_id).json()["estado"] == "completado"
    assert _fila(cliente, sesion_id).fotogramas_analizados == 1
    assert _segundos_guardados(cliente, sesion_id) == [3.0]
    assert cliente.get(f"/analisis/{sesion_id}/informe").json()["marcas"][0]["segundos"] == 5.0


def test_cerrar_sin_fotogramas_la_deja_fallida(cliente):
    sesion_id = abrir_sesion(cliente).json()["id"]
    cierre = _cerrar(cliente, sesion_id)
    assert cierre.status_code == 200
    assert (cierre.json()["estado"], cierre.json()["error"]) == ("fallido", ERROR_SIN_FOTOGRAMAS)
    assert cliente.get(f"/analisis/{sesion_id}/informe").json() == {"detail": SIN_RESULTADOS}
    otra_vez = _cerrar(cliente, sesion_id)
    assert otra_vez.status_code == 409
    assert otra_vez.json() == {"detail": SESION_FALLIDA}


def test_cerrar_dos_veces_no_cambia_nada(cliente):
    sesion_id = abrir_sesion(cliente).json()["id"]
    enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48))
    primera = _cerrar(cliente, sesion_id)
    terminado = _fila(cliente, sesion_id).terminado
    segunda = _cerrar(cliente, sesion_id)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert _fila(cliente, sesion_id).terminado == terminado


def test_una_sesion_cerrada_no_admite_mas_fotogramas(cliente, api_modelo):
    sesion_id = abrir_sesion(cliente).json()["id"]
    enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48))
    _cerrar(cliente, sesion_id)
    respuesta = enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48), t_s=5)
    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": SESION_TERMINADA}
    assert api_modelo.llamadas_predict == 1
    assert _fila(cliente, sesion_id).fotogramas_analizados == 1


def test_sesion_inexistente_o_del_modo_informe_responde_404(cliente, api_modelo, crear_video, subir, esperar_analisis):
    analisis_informe = subir(cliente, crear_video(segundos=1)).json()["id"]
    esperar_analisis(cliente, analisis_informe)
    llamadas = api_modelo.llamadas_predict
    for identificador in (str(uuid.uuid4()), "no-es-un-uuid", analisis_informe):
        fotograma = enviar_fotograma(cliente, identificador, crear_imagen(64, 48))
        cierre = _cerrar(cliente, identificador)
        assert fotograma.status_code == cierre.status_code == 404
        assert fotograma.json() == cierre.json() == {"detail": NO_ENCONTRADO}
    assert api_modelo.llamadas_predict == llamadas
    assert _fila(cliente, analisis_informe).estado == "completado"


@pytest.mark.parametrize("campos", [
    {"duracion_s": 0}, {"duracion_s": -5}, {"duracion_s": "nan"}, {"duracion_s": "inf"}, {"duracion_s": None},
    {"umbral": 0.04}, {"umbral": 0.96}, {"nombre_video": None},
])
def test_parametros_no_validos_al_abrir_reciben_422(cliente, campos):
    assert abrir_sesion(cliente, **campos).status_code == 422


def test_mismo_limite_de_2_minutos_que_el_modo_informe(cliente):
    respuesta = abrir_sesion(cliente, duracion_s=120.5)
    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": DEMASIADO_LARGO}
    assert abrir_sesion(cliente, duracion_s=120).status_code == 201


def test_el_nombre_del_video_se_limpia_como_en_las_subidas(cliente):
    for nombre, esperado in (("C:\\videos\\partido\x07.mp4", "partido.mp4"), ("a" * 300 + ".mp4", "a" * 255)):
        sesion_id = abrir_sesion(cliente, nombre_video=nombre).json()["id"]
        assert cliente.get(f"/analisis/{sesion_id}").json()["nombre_video"] == esperado


def test_con_modos_informe_se_siguen_sirviendo_las_sesiones_guardadas(crear_cliente, api_modelo):
    api_modelo.por_defecto = [NIKE]
    con_en_vivo = crear_cliente()
    sesion_id = abrir_sesion(con_en_vivo).json()["id"]
    enviar_fotograma(con_en_vivo, sesion_id, crear_imagen(64, 48))
    _cerrar(con_en_vivo, sesion_id)

    solo_informe = crear_cliente(modos=("informe",))
    for ruta in ("", "/informe", "/detecciones"):
        assert solo_informe.get(f"/analisis/{sesion_id}{ruta}").status_code == 200
    assert _cerrar(solo_informe, sesion_id).status_code == 404
