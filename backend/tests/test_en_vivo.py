"""Modo en vivo: fotogramas, validación, límite por minuto y desactivación por MODOS."""

import pytest

from conftest import abrir_sesion, crear_imagen, enviar_fotograma
from main import DEMASIADAS_PETICIONES
from rutas import MODELO_NO_RESPONDE
from rutas_en_vivo import FORMATO_IMAGEN, SEGUNDO_FUERA_DEL_VIDEO

PEPSI = {"marca": "Pepsi", "confianza": 0.91, "caja": [64, 36, 128, 72]}


@pytest.fixture
def sesion_id(cliente) -> str:
    return abrir_sesion(cliente).json()["id"]


def test_devuelve_las_detecciones_con_el_mismo_segundo(cliente, api_modelo):
    api_modelo.por_defecto = [PEPSI]
    sesion_id = abrir_sesion(cliente, umbral=0.5).json()["id"]
    respuesta = enviar_fotograma(cliente, sesion_id, crear_imagen(1280, 720), t_s=12.34)
    assert respuesta.status_code == 200
    # La API recibió 640 px de lado y las cajas vuelven en píxeles de la imagen enviada
    assert api_modelo.imagenes_recibidas == [(640, 360)]
    assert api_modelo.umbrales_recibidos == [0.5]
    assert respuesta.json() == {
        "t_s": 12.34,
        "detecciones": [{"marca": "Pepsi", "confianza": 0.91, "caja": [128.0, 72.0, 256.0, 144.0]}],
    }


def test_acepta_png_y_usa_el_umbral_de_la_sesion(cliente, api_modelo, sesion_id):
    # El umbral del formulario ya no existe: si llega, se ignora
    respuesta = enviar_fotograma(cliente, sesion_id, crear_imagen(320, 240, ".png"), nombre="fotograma.png", umbral=0.3)
    assert respuesta.status_code == 200
    assert respuesta.json() == {"t_s": 1.5, "detecciones": []}
    assert api_modelo.imagenes_recibidas == [(320, 240)]
    assert api_modelo.umbrales_recibidos == [0.775]


def test_mas_de_30_fotogramas_por_minuto_reciben_429(cliente, sesion_id):
    for _ in range(30):
        assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48)).status_code == 200
    bloqueado = enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48))
    assert bloqueado.status_code == 429
    assert bloqueado.json() == {"detail": DEMASIADAS_PETICIONES}
    # Otra IP tiene su propio contador
    otra_ip = {"True-Client-IP": "198.51.100.4"}
    assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48), headers=otra_ip).status_code == 200


def test_el_limite_se_relaja_con_la_variable(crear_cliente):
    cliente = crear_cliente(limite_en_vivo_por_minuto=40)
    sesion_id = abrir_sesion(cliente).json()["id"]
    for _ in range(40):
        assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48)).status_code == 200
    assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48)).status_code == 429


@pytest.mark.parametrize("datos", [
    b"texto que no es una imagen",
    b"GIF89a" + b"\x00" * 100,
    b"\xff\xd8\xff" + b"\x00" * 100,  # empieza como un JPEG pero no lo es
])
def test_formato_no_admitido_recibe_415(cliente, api_modelo, sesion_id, datos):
    respuesta = enviar_fotograma(cliente, sesion_id, datos)
    assert respuesta.status_code == 415
    assert respuesta.json() == {"detail": FORMATO_IMAGEN}
    assert api_modelo.llamadas_predict == 0


def test_imagen_demasiado_grande_recibe_413(cliente, api_modelo, sesion_id):
    mas_de_2_mb = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)
    assert enviar_fotograma(cliente, sesion_id, mas_de_2_mb).status_code == 413
    for ancho, alto, formato in ((2000, 100, ".jpg"), (100, 1921, ".png"), (2000, 2000, ".png")):
        assert enviar_fotograma(cliente, sesion_id, crear_imagen(ancho, alto, formato)).status_code == 413
    assert enviar_fotograma(cliente, sesion_id, crear_imagen(1920, 1920, ".png")).status_code == 200
    assert api_modelo.llamadas_predict == 1


@pytest.mark.parametrize("campos", [
    {"t_s": -1}, {"t_s": "inf"}, {"t_s": "nan"}, {"t_s": "uno"}, {"t_s": None}, {"sesion_id": None},
])
def test_parametros_no_validos_reciben_422(cliente, api_modelo, sesion_id, campos):
    valores = {"sesion_id": sesion_id, **campos}
    respuesta = enviar_fotograma(cliente, valores.pop("sesion_id"), crear_imagen(64, 48), **valores)
    assert respuesta.status_code == 422
    assert api_modelo.llamadas_predict == 0


def test_un_segundo_posterior_al_final_del_video_recibe_422(cliente, api_modelo):
    sesion_id = abrir_sesion(cliente, duracion_s=10).json()["id"]
    respuesta = enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48), t_s=10.01)
    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": SEGUNDO_FUERA_DEL_VIDEO}
    assert api_modelo.llamadas_predict == 0
    # El último instante del vídeo sí vale
    assert enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48), t_s=10).status_code == 200


def test_si_la_api_del_modelo_falla_recibe_502(cliente, api_modelo, sesion_id):
    api_modelo.por_defecto = "error"
    respuesta = enviar_fotograma(cliente, sesion_id, crear_imagen(64, 48))
    assert respuesta.status_code == 502
    assert respuesta.json() == {"detail": MODELO_NO_RESPONDE}
    assert api_modelo.llamadas_predict == 2  # se reintenta una vez


def test_con_modos_informe_los_endpoints_no_existen(crear_cliente, api_modelo):
    cliente = crear_cliente(modos=("informe",))
    sesion = abrir_sesion(cliente)
    assert sesion.status_code == 404
    assert enviar_fotograma(cliente, "00000000-0000-0000-0000-000000000000", crear_imagen(64, 48)).status_code == 404
    assert cliente.post("/en-vivo/sesion/00000000-0000-0000-0000-000000000000/fin").status_code == 404
    assert api_modelo.llamadas_predict == 0
    modos = cliente.get("/config").json()["modos"]
    assert modos == ["informe"]
    assert "en_vivo" not in modos
