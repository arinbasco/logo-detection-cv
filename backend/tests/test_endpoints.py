"""Endpoints generales: salud, configuración, marcas, documentación, cabeceras, CORS y límites."""

from conftest import MARCAS
from main import DEMASIADAS_PETICIONES, ERROR_INTERNO
from rutas import MODELO_NO_RESPONDE

CABECERAS = {"x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "cache-control": "no-store"}


def test_salud(cliente):
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_config_con_los_dos_modos(cliente):
    assert cliente.get("/config").json() == {"modos": ["informe", "en_vivo"], "segundos_por_fotograma": 3.5}


def test_marcas_leidas_de_la_api_del_modelo(cliente):
    respuesta = cliente.get("/marcas")
    assert respuesta.status_code == 200
    assert respuesta.json() == MARCAS
    assert len(respuesta.json()) == 15


def test_marcas_502_si_la_api_del_modelo_no_responde(crear_cliente, api_modelo):
    api_modelo.fallar_estado = True
    respuesta = crear_cliente().get("/marcas")
    assert respuesta.status_code == 502
    assert respuesta.json() == {"detail": MODELO_NO_RESPONDE}


def test_docs_devuelve_404_con_mostrar_docs_0(cliente):
    for ruta in ("/docs", "/openapi.json", "/redoc"):
        assert cliente.get(ruta).status_code == 404


def test_docs_disponibles_con_mostrar_docs_1(crear_cliente):
    cliente = crear_cliente(mostrar_docs=True)
    assert cliente.get("/docs").status_code == 200
    assert cliente.get("/openapi.json").status_code == 200


ERRORES_DOCUMENTADOS = {
    ("get", "/salud"): {429},
    ("get", "/config"): {429},
    ("get", "/marcas"): {429, 502},
    ("post", "/analisis"): {413, 415, 422, 429},
    ("get", "/analisis/{analisis_id}"): {404, 429},
    ("get", "/analisis/{analisis_id}/informe"): {404, 409, 429},
    ("get", "/analisis/{analisis_id}/detecciones"): {404, 409, 422, 429},
    ("get", "/recortes/{recorte_id}"): {404, 429},
    ("post", "/en-vivo/sesion"): {422, 429},
    ("post", "/en-vivo/fotograma"): {404, 409, 413, 415, 422, 429, 502},
    ("post", "/en-vivo/sesion/{sesion_id}/fin"): {404, 409, 429},
}


def test_openapi_documenta_los_errores_reales_de_cada_endpoint(crear_cliente):
    esquema = crear_cliente(mostrar_docs=True).get("/openapi.json").json()
    operaciones = {(metodo, ruta): op for ruta, ops in esquema["paths"].items() for metodo, op in ops.items()}
    assert set(operaciones) == set(ERRORES_DOCUMENTADOS)
    for clave, operacion in operaciones.items():
        codigos = {int(codigo) for codigo in operacion["responses"] if int(codigo) >= 400}
        assert codigos == ERRORES_DOCUMENTADOS[clave], clave
        for codigo in codigos:
            respuesta = operacion["responses"][str(codigo)]
            assert respuesta["content"] == {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}
            assert respuesta["description"]
    esquemas = esquema["components"]["schemas"]
    assert esquemas["Error"]["properties"] == {"detail": {"type": "string", "title": "Detail"}}
    assert esquemas["Error"]["required"] == ["detail"]
    # El 422 que FastAPI añade por su cuenta describe un cuerpo que el backend nunca devuelve
    assert "HTTPValidationError" not in esquemas and "ValidationError" not in esquemas


def test_openapi_sin_en_vivo_no_documenta_sus_endpoints(crear_cliente):
    esquema = crear_cliente(mostrar_docs=True, modos=("informe",)).get("/openapi.json").json()
    assert not [ruta for ruta in esquema["paths"] if ruta.startswith("/en-vivo")]


def test_cabeceras_de_seguridad_en_todas_las_respuestas(cliente):
    respuestas = [
        cliente.get("/salud"),
        cliente.get("/no-existe"),
        cliente.post("/salud"),
        cliente.post("/analisis", data={"intervalo_s": "9"}),
    ]
    assert [r.status_code for r in respuestas] == [200, 404, 405, 422]
    for respuesta in respuestas:
        for nombre, valor in CABECERAS.items():
            assert respuesta.headers.get(nombre) == valor


def test_cors_solo_para_el_origen_del_front(cliente):
    permitido = cliente.get("/salud", headers={"Origin": "http://front.prueba"})
    assert permitido.headers.get("access-control-allow-origin") == "http://front.prueba"
    ajeno = cliente.get("/salud", headers={"Origin": "http://otro.prueba"})
    assert "access-control-allow-origin" not in ajeno.headers
    previa = cliente.options("/analisis", headers={
        "Origin": "http://front.prueba", "Access-Control-Request-Method": "POST",
    })
    assert previa.status_code == 200
    assert previa.headers.get("access-control-allow-origin") == "http://front.prueba"


def test_sin_front_origin_no_se_admite_ningun_origen(crear_cliente):
    cliente = crear_cliente(front_origin=None)
    respuesta = cliente.get("/salud", headers={"Origin": "http://front.prueba"})
    assert "access-control-allow-origin" not in respuesta.headers


def test_limite_general_de_120_por_minuto_por_ip(cliente):
    for _ in range(120):
        assert cliente.get("/salud").status_code == 200
    bloqueada = cliente.get("/salud")
    assert bloqueada.status_code == 429
    assert bloqueada.json() == {"detail": DEMASIADAS_PETICIONES}
    # El límite es por endpoint y por IP: otro endpoint u otra IP siguen respondiendo
    assert cliente.get("/config").status_code == 200
    assert cliente.get("/salud", headers={"True-Client-IP": "203.0.113.7"}).status_code == 200


def test_una_true_client_ip_no_valida_se_ignora(cliente):
    for _ in range(120):
        assert cliente.get("/salud", headers={"True-Client-IP": "no es una IP"}).status_code == 200
    # Se contó con la IP de la conexión, que ya agotó su límite
    assert cliente.get("/salud").status_code == 429


def test_error_interno_con_mensaje_generico(crear_cliente):
    cliente = crear_cliente(lanzar_errores=False)

    def fallar():
        raise RuntimeError("detalle interno que no debe salir")

    cliente.app.state.contexto.cliente.media.valor = fallar
    respuesta = cliente.get("/config")
    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": ERROR_INTERNO}
    assert "detalle interno" not in respuesta.text
    for nombre, valor in CABECERAS.items():
        assert respuesta.headers.get(nombre) == valor
