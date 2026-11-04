"""Configuración del backend, leída de variables de entorno.

En local las variables se leen también del archivo .env de la raíz del repositorio, si
existe. Nunca se sobrescribe una variable ya definida, así que en Render, donde no hay
.env, mandan las variables configuradas en el servicio.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

CARPETA_BACKEND = Path(__file__).resolve().parent
load_dotenv(CARPETA_BACKEND.parent / ".env", override=False)

MODOS_VALIDOS = ("informe", "en_vivo")
LIMITE_EN_VIVO_POR_DEFECTO = 30  # peticiones por minuto e IP, el valor de la especificación


def _leer(nombre: str) -> str:
    return os.getenv(nombre, "").strip()


def _obligatoria(nombre: str) -> str:
    valor = _leer(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre}")
    return valor


def _url_http(nombre: str, valor: str) -> str:
    if not valor.startswith(("http://", "https://")):
        raise RuntimeError(f"{nombre} debe empezar por http:// o https://")
    return valor.rstrip("/")


def url_base_datos() -> str:
    """Cadena de conexión de DATABASE_URL. La usan la app y las migraciones."""
    return _obligatoria("DATABASE_URL")


def _modos(texto: str) -> tuple[str, ...]:
    pedidos = {modo.strip() for modo in texto.split(",") if modo.strip()}
    desconocidos = pedidos - set(MODOS_VALIDOS)
    if desconocidos or not pedidos:
        raise RuntimeError(f"MODOS solo admite {', '.join(MODOS_VALIDOS)}, separados por comas")
    return tuple(modo for modo in MODOS_VALIDOS if modo in pedidos)


def _limite_en_vivo(texto: str) -> int:
    if not texto:
        return LIMITE_EN_VIVO_POR_DEFECTO
    if not texto.isdigit() or int(texto) < 1:
        raise RuntimeError("LIMITE_EN_VIVO_POR_MINUTO debe ser un número entero mayor que 0")
    return int(texto)


@dataclass(frozen=True)
class Ajustes:
    """Valores de configuración. La clave y la cadena de conexión no salen en su repr."""

    model_api_url: str
    model_api_key: str = field(repr=False)
    database_url: str = field(repr=False)
    modos: tuple[str, ...]
    front_origin: str | None = None
    mostrar_docs: bool = False
    limite_en_vivo_por_minuto: int = LIMITE_EN_VIVO_POR_DEFECTO

    @property
    def en_vivo(self) -> bool:
        return "en_vivo" in self.modos

    @classmethod
    def desde_entorno(cls) -> "Ajustes":
        origen = _leer("FRONT_ORIGIN")
        return cls(
            model_api_url=_url_http("MODEL_API_URL", _obligatoria("MODEL_API_URL")),
            model_api_key=_obligatoria("MODEL_API_KEY"),
            database_url=url_base_datos(),
            modos=_modos(_obligatoria("MODOS")),
            front_origin=_url_http("FRONT_ORIGIN", origen) if origen else None,
            # Sin la variable, la documentación queda desactivada, que es lo más seguro
            mostrar_docs=_leer("MOSTRAR_DOCS") == "1",
            limite_en_vivo_por_minuto=_limite_en_vivo(_leer("LIMITE_EN_VIVO_POR_MINUTO")),
        )
