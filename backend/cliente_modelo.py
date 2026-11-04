"""Cliente de la API del modelo. Es la única pieza que conoce su dirección y su clave."""

import logging
import math
import threading
import time
from collections import deque

import httpx
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("backend.modelo")

TIEMPO_LIMITE_S = 30.0
SEGUNDOS_INICIALES = 3.5  # media de partida: lo que tarda la API desplegada en Render
LLAMADAS_EN_MEDIA = 20


class ErrorModelo(Exception):
    """La API del modelo no respondió o respondió algo con un formato inesperado."""


class DeteccionModelo(BaseModel):
    marca: str = Field(min_length=1, max_length=100)
    confianza: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    caja: list[float] = Field(min_length=4, max_length=4)

    @field_validator("caja")
    @classmethod
    def _caja_finita(cls, caja: list[float]) -> list[float]:
        if not all(math.isfinite(valor) for valor in caja):
            raise ValueError("la caja tiene valores no finitos")
        return caja


class RespuestaPrediccion(BaseModel):
    detecciones: list[DeteccionModelo]


class RespuestaEstado(BaseModel):
    marcas: list[str] = Field(min_length=1)

    @field_validator("marcas")
    @classmethod
    def _marcas_con_nombre(cls, marcas: list[str]) -> list[str]:
        if not all(marca.strip() for marca in marcas):
            raise ValueError("hay marcas sin nombre")
        return marcas


class MediaMovil:
    """Media en segundos de las últimas llamadas correctas a la API del modelo.

    Mientras no hay ninguna medida se usa el valor inicial.
    """

    def __init__(self, inicial: float = SEGUNDOS_INICIALES, tamano: int = LLAMADAS_EN_MEDIA):
        self._inicial = inicial
        self._valores: deque[float] = deque(maxlen=tamano)
        self._candado = threading.Lock()

    def anadir(self, segundos: float) -> None:
        with self._candado:
            self._valores.append(segundos)

    def valor(self) -> float:
        with self._candado:
            if not self._valores:
                return self._inicial
            return sum(self._valores) / len(self._valores)


def _describir(error: Exception) -> str:
    """Describe un fallo para los registros sin URL, cabeceras ni contenido de la petición."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"respuesta {error.response.status_code}"
    return type(error).__name__


class ClienteModelo:
    def __init__(self, url_base: str, clave: str, transporte: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=url_base,
            headers={"X-API-Key": clave},
            timeout=TIEMPO_LIMITE_S,
            transport=transporte,
        )
        self.media = MediaMovil()
        self._marcas: list[str] | None = None
        self._candado_marcas = threading.Lock()

    def cerrar(self) -> None:
        self._http.close()

    def marcas(self) -> list[str]:
        """Marcas que reconoce el modelo, leídas de GET / la primera vez que se piden."""
        with self._candado_marcas:
            if self._marcas is None:
                try:
                    respuesta = self._http.get("/")
                    respuesta.raise_for_status()
                    self._marcas = RespuestaEstado.model_validate(respuesta.json()).marcas
                except (httpx.HTTPError, ValueError) as error:
                    logger.warning("No se pudo leer la lista de marcas: %s", _describir(error))
                    raise ErrorModelo() from None
            return list(self._marcas)

    def predecir(self, imagen_jpeg: bytes, umbral: float) -> list[DeteccionModelo]:
        """Envía una imagen a la API del modelo y devuelve sus detecciones validadas.

        Si la llamada falla o la respuesta no tiene el formato esperado, reintenta una vez.
        """
        for intento in (1, 2):
            inicio = time.monotonic()
            try:
                respuesta = self._http.post(
                    "/predict",
                    params={"conf": umbral},
                    files={"imagen": ("fotograma.jpg", imagen_jpeg, "image/jpeg")},
                )
                respuesta.raise_for_status()
                detecciones = RespuestaPrediccion.model_validate(respuesta.json()).detecciones
                conocidas = self._marcas
                if conocidas is not None and any(d.marca not in conocidas for d in detecciones):
                    raise ValueError("marca desconocida")
            except (httpx.HTTPError, ValueError) as error:
                logger.warning("La API del modelo falló (intento %d de 2): %s", intento, _describir(error))
                continue
            self.media.anadir(time.monotonic() - inicio)
            return detecciones
        raise ErrorModelo()
