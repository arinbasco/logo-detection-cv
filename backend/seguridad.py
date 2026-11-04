"""Protecciones comunes: límites de uso por IP, tamaño de las subidas y cabeceras de seguridad."""

import ipaddress
import json
from collections.abc import Callable

from fastapi import HTTPException, Request
from slowapi import Limiter

LIMITE_GENERAL = "120/minute"  # por IP y por endpoint, salvo el modo en vivo

MAX_BYTES_VIDEO = 100 * 1024 * 1024
MAX_BYTES_FOTOGRAMA = 2 * 1024 * 1024
# Lo que ocupan los separadores y los demás campos del formulario, además del archivo
MARGEN_FORMULARIO = 64 * 1024

ANALISIS_EN_CURSO = "Ya hay un análisis en curso. Inténtalo cuando termine."
VIDEO_GRANDE = "El vídeo supera los 100 MB."
FOTOGRAMA_GRANDE = "La imagen supera los 2 MB."

CABECERAS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
]


def ip_cliente(request: Request) -> str:
    """IP con la que se cuentan los límites de uso.

    En Render las peticiones llegan a través de Cloudflare, que sobrescribe la cabecera
    True-Client-IP con la IP real. X-Forwarded-For no se usa porque el cliente puede
    falsificarla. Sin esa cabecera, como en local, se usa la IP de la conexión.
    """
    cabecera = request.headers.get("true-client-ip", "").strip()
    if cabecera:
        try:
            return str(ipaddress.ip_address(cabecera))
        except ValueError:
            pass
    return request.client.host if request.client else "desconocida"


def crear_limitador() -> Limiter:
    """Límite general por IP y endpoint, con ventana deslizante de un minuto, en memoria."""
    return Limiter(
        key_func=ip_cliente,
        default_limits=[LIMITE_GENERAL],
        strategy="moving-window",
        key_style="endpoint",
    )


async def _responder(send, estado: int, detalle: str) -> None:
    cuerpo = json.dumps({"detail": detalle}, ensure_ascii=False).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": estado,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())],
    })
    await send({"type": "http.response.body", "body": cuerpo})


class LimiteCuerpo:
    """Corta las subidas que superan el tamaño máximo mientras se reciben.

    FastAPI guarda el archivo entero antes de llamar al endpoint, así que el límite se
    aplica aquí, contando los bytes según llegan. Si se supera, se responde 413 y lo
    recibido hasta entonces se descarta. También rechaza con 429 un análisis nuevo
    mientras hay otro en curso, antes de recibir el vídeo.
    """

    def __init__(self, app, analisis_en_curso: Callable[[], bool]):
        self.app = app
        self.analisis_en_curso = analisis_en_curso
        self.limites = {
            ("POST", "/analisis"): (MAX_BYTES_VIDEO + MARGEN_FORMULARIO, VIDEO_GRANDE),
            ("POST", "/en-vivo/fotograma"): (MAX_BYTES_FOTOGRAMA + MARGEN_FORMULARIO, FOTOGRAMA_GRANDE),
        }

    async def __call__(self, scope, receive, send) -> None:
        clave = (scope.get("method"), scope.get("path"))
        if scope["type"] != "http" or clave not in self.limites:
            await self.app(scope, receive, send)
            return
        if clave == ("POST", "/analisis") and self.analisis_en_curso():
            await _responder(send, 429, ANALISIS_EN_CURSO)
            return

        limite, mensaje = self.limites[clave]
        longitud = dict(scope.get("headers", [])).get(b"content-length")
        if longitud is not None and longitud.isdigit() and int(longitud) > limite:
            await _responder(send, 413, mensaje)
            return

        recibidos = 0
        excedido = False

        async def recibir_con_limite():
            nonlocal recibidos, excedido
            mensaje_asgi = await receive()
            if mensaje_asgi["type"] == "http.request":
                recibidos += len(mensaje_asgi.get("body", b""))
                if recibidos > limite:
                    excedido = True
                    raise HTTPException(status_code=413, detail=mensaje)
            return mensaje_asgi

        respondido = False

        async def enviar(mensaje_asgi) -> None:
            nonlocal respondido
            if not excedido:
                await send(mensaje_asgi)
            elif not respondido:
                # Pase lo que pase dentro de la app, el cliente recibe el mismo 413
                respondido = True
                await _responder(send, 413, mensaje)

        try:
            await self.app(scope, recibir_con_limite, enviar)
        except HTTPException:
            if not excedido:
                raise
            if not respondido:
                await _responder(send, 413, mensaje)


class CabecerasSeguridad:
    """Añade nosniff, no-referrer y no-store a todas las respuestas."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def enviar(mensaje) -> None:
            if mensaje["type"] == "http.response.start":
                cabeceras = list(mensaje.get("headers", []))
                presentes = {nombre.lower() for nombre, _ in cabeceras}
                cabeceras += [c for c in CABECERAS if c[0] not in presentes]
                mensaje = {**mensaje, "headers": cabeceras}
            await send(mensaje)

        await self.app(scope, receive, enviar)
