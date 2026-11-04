"""Modelos de respuesta. Solo exponen los campos definidos en la especificación."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


LIMITE_POR_IP = "Demasiadas peticiones seguidas desde la misma IP."


class Error(BaseModel):
    """Cuerpo de todas las respuestas de error: un mensaje genérico, sin detalles internos."""

    detail: str


def errores(descripciones: dict[int, str] | None = None) -> dict[int, dict[str, Any]]:
    """Respuestas de error de un endpoint para el OpenAPI, con el cuerpo {"detail": "texto"}.

    Todas incluyen el 429 del límite de peticiones por IP, salvo que se describa otro.
    """
    descripciones = {429: LIMITE_POR_IP, **(descripciones or {})}
    return {codigo: {"model": Error, "description": texto} for codigo, texto in sorted(descripciones.items())}


class Salud(BaseModel):
    estado: str


class Configuracion(BaseModel):
    modos: list[str]
    segundos_por_fotograma: float


class AnalisisCreado(BaseModel):
    id: uuid.UUID
    estado: str
    tiempo_estimado_s: float


class SesionCreada(BaseModel):
    id: uuid.UUID


class EstadoAnalisis(BaseModel):
    id: uuid.UUID
    nombre_video: str
    modo: str
    estado: str
    progreso: float
    duracion_s: float
    fps: float | None  # null en las sesiones en vivo
    intervalo_s: float | None  # null en las sesiones en vivo
    umbral: float
    creado: datetime
    error: str | None
    tiempo_restante_s: float


class MarcaInforme(BaseModel):
    marca: str
    segundos: float
    porcentaje: float
    detecciones: int
    confianza_media: float


class Hallazgo(BaseModel):
    tipo: str
    datos: dict[str, Any]


class Informe(BaseModel):
    marcas: list[MarcaInforme]
    resumen: str
    hallazgos: list[Hallazgo]


class DeteccionGuardada(BaseModel):
    id: uuid.UUID
    t_s: float
    marca: str
    confianza: float
    caja: list[int]
    recorte_id: uuid.UUID


class DeteccionEnVivo(BaseModel):
    marca: str
    confianza: float
    caja: list[float]


class RespuestaEnVivo(BaseModel):
    t_s: float
    detecciones: list[DeteccionEnVivo]
