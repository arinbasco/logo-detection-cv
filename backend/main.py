"""Backend de la app de detección de logos.

Recibe vídeos, los analiza con la API del modelo, guarda las detecciones y sus recortes y
sirve el informe de tiempo en pantalla por marca. En la versión local hace además de
intermediario del modo en vivo.
"""

import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from basedatos import crear_motor, crear_sesiones
from cliente_modelo import ClienteModelo, ErrorModelo
from config import Ajustes
from procesamiento import GestorAnalisis, borrar_antiguos, limpiar_temporales, recuperar_tras_reinicio
from rutas import NO_ENCONTRADO, Contexto, registrar_rutas
from rutas_en_vivo import registrar_rutas_en_vivo
from seguridad import CABECERAS, CabecerasSeguridad, LimiteCuerpo, crear_limitador

CARPETA_TEMPORAL = Path(tempfile.gettempdir()) / "logos-backend"

PARAMETROS_NO_VALIDOS = "Parámetros no válidos o fuera de rango."
DEMASIADAS_PETICIONES = "Demasiadas peticiones. Espera un momento antes de volver a intentarlo."
METODO_NO_PERMITIDO = "Método no permitido."
ERROR_INTERNO = "Error interno del servidor."

logger = logging.getLogger("backend")


def _configurar_registros() -> None:
    if not logger.handlers:
        manejador = logging.StreamHandler()
        manejador.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(manejador)
        logger.setLevel(logging.INFO)
    # httpx registra cada petición con su URL y slowapi la IP del cliente: solo errores graves
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("slowapi").setLevel(logging.ERROR)


def _precargar_marcas(cliente: ClienteModelo) -> None:
    """Pide la lista de marcas al arrancar, sin bloquear el arranque si la API está dormida."""
    try:
        cliente.marcas()
    except ErrorModelo:
        pass  # se vuelve a pedir en la primera llamada a /marcas


def _registrar_errores(app: FastAPI) -> None:
    """Respuestas de error genéricas. El detalle técnico solo va a los registros del servidor."""

    @app.exception_handler(StarletteHTTPException)
    async def error_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            detalle = NO_ENCONTRADO
        elif exc.status_code == 405:
            detalle = METODO_NO_PERMITIDO
        else:
            detalle = exc.detail if isinstance(exc.detail, str) else ERROR_INTERNO
        return JSONResponse(status_code=exc.status_code, content={"detail": detalle}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def error_validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
        # No se devuelven los valores recibidos, solo un mensaje genérico
        return JSONResponse(status_code=422, content={"detail": PARAMETROS_NO_VALIDOS})

    @app.exception_handler(RateLimitExceeded)
    async def error_limite(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": DEMASIADAS_PETICIONES})

    @app.exception_handler(Exception)
    async def error_interno(request: Request, exc: Exception) -> JSONResponse:
        ruta = getattr(request.scope.get("route"), "path", "desconocida")
        logger.error("Error no controlado en %s %s", request.method, ruta, exc_info=exc)
        cabeceras = {nombre.decode(): valor.decode() for nombre, valor in CABECERAS}
        return JSONResponse(status_code=500, content={"detail": ERROR_INTERNO}, headers=cabeceras)


def _documentar_solo_errores_reales(app: FastAPI) -> None:
    """Quita del OpenAPI el 422 que FastAPI añade solo a todo endpoint con parámetros.

    Ese 422 describe una lista de errores de validación que el backend nunca devuelve, porque
    responde siempre {"detail": "texto"}. Los endpoints que sí pueden dar 422 lo declaran
    con sus demás errores.
    """
    generar = app.openapi

    def openapi() -> dict:
        esquema = generar()  # FastAPI lo genera una vez y después devuelve el mismo
        for operaciones in esquema.get("paths", {}).values():
            for operacion in operaciones.values():
                respuesta = operacion.get("responses", {}).get("422", {})
                if "HTTPValidationError" in str(respuesta):
                    del operacion["responses"]["422"]
        for nombre in ("HTTPValidationError", "ValidationError"):
            esquema.get("components", {}).get("schemas", {}).pop(nombre, None)
        return esquema

    app.openapi = openapi


def crear_app(
    ajustes: Ajustes | None = None,
    transporte: httpx.BaseTransport | None = None,
    carpeta_temporal: Path | None = None,
) -> FastAPI:
    """Monta la aplicación. Los tests pasan en transporte una API del modelo simulada."""
    _configurar_registros()
    ajustes = ajustes or Ajustes.desde_entorno()
    motor = crear_motor(ajustes.database_url)
    sesiones = crear_sesiones(motor)
    cliente = ClienteModelo(ajustes.model_api_url, ajustes.model_api_key, transporte)
    carpeta = carpeta_temporal or CARPETA_TEMPORAL
    gestor = GestorAnalisis(sesiones, cliente, carpeta)

    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI):
        limpiar_temporales(carpeta)
        interrumpidos = recuperar_tras_reinicio(sesiones)
        if interrumpidos:
            logger.warning("%d análisis o sesiones en vivo sin terminar quedan como fallidos", interrumpidos)
        borrados = borrar_antiguos(sesiones)
        if borrados:
            logger.info("%d análisis de más de 7 días borrados", borrados)
        threading.Thread(target=_precargar_marcas, args=(cliente,), daemon=True).start()
        yield
        cliente.cerrar()
        motor.dispose()

    app = FastAPI(
        title="Backend de detección de logos",
        version="1.0",
        docs_url="/docs" if ajustes.mostrar_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if ajustes.mostrar_docs else None,
        lifespan=ciclo_de_vida,
    )
    limitador = crear_limitador()
    app.state.limiter = limitador
    app.state.contexto = Contexto(ajustes, sesiones, cliente, gestor)

    registrar_rutas(app)
    if ajustes.en_vivo:
        registrar_rutas_en_vivo(app, limitador, ajustes.limite_en_vivo_por_minuto)
    _registrar_errores(app)
    _documentar_solo_errores_reales(app)

    # El último middleware añadido es el primero que recibe la petición
    app.add_middleware(LimiteCuerpo, analisis_en_curso=lambda: gestor.ocupado)
    app.add_middleware(SlowAPIASGIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ajustes.front_origin] if ajustes.front_origin else [],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(CabecerasSeguridad)
    return app


app = crear_app()
