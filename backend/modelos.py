"""Tablas de la base de datos: analisis, deteccion, recorte y fotograma.

Los recortes van en su propia tabla para que listar detecciones no cargue imágenes.
Los identificadores son UUID aleatorios para que no se puedan adivinar.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

ESTADOS = ("en_cola", "procesando", "completado", "fallido")

# Nombres fijos para restricciones e índices, iguales en Postgres, SQLite y las migraciones
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class FechaUTC(TypeDecorator):
    """Fecha y hora en UTC. SQLite no guarda la zona horaria, así que se guarda sin ella."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valor: datetime | None, dialecto) -> datetime | None:
        if valor is None:
            return None
        if valor.tzinfo is None:
            raise ValueError("La fecha debe llevar zona horaria")
        valor = valor.astimezone(timezone.utc)
        return valor.replace(tzinfo=None) if dialecto.name == "sqlite" else valor

    def process_result_value(self, valor: datetime | None, dialecto) -> datetime | None:
        if valor is None:
            return None
        if valor.tzinfo is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)


class Analisis(Base):
    __tablename__ = "analisis"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('en_cola', 'procesando', 'completado', 'fallido')", name="estado"
        ),
        CheckConstraint("modo IN ('informe', 'en_vivo')", name="modo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre_video: Mapped[str] = mapped_column(String(255))  # solo para mostrar, nunca es una ruta
    # informe para los vídeos subidos, en_vivo para las sesiones del modo en vivo
    modo: Mapped[str] = mapped_column(Text, default="informe", server_default="informe")
    estado: Mapped[str] = mapped_column(Text)
    progreso: Mapped[float] = mapped_column(Float)  # de 0 a 1
    duracion_s: Mapped[float] = mapped_column(Float)
    # Las sesiones en vivo no tienen fps ni un intervalo fijo entre fotogramas
    fps: Mapped[float | None] = mapped_column(Float)
    intervalo_s: Mapped[float | None] = mapped_column(Float)
    umbral: Mapped[float] = mapped_column(Float)
    fotogramas_analizados: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)  # mensaje genérico, sin detalles internos
    creado: Mapped[datetime] = mapped_column(FechaUTC)
    terminado: Mapped[datetime | None] = mapped_column(FechaUTC)


class Recorte(Base):
    __tablename__ = "recorte"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    datos: Mapped[bytes] = mapped_column(LargeBinary)  # JPEG de 256 píxeles de lado como máximo


class Deteccion(Base):
    __tablename__ = "deteccion"
    __table_args__ = (
        Index("ix_deteccion_analisis_id_t_s", "analisis_id", "t_s"),
        Index("ix_deteccion_recorte_id", "recorte_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analisis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analisis.id", ondelete="CASCADE")
    )
    t_s: Mapped[float] = mapped_column(Float)  # segundo del vídeo
    marca: Mapped[str] = mapped_column(Text)
    confianza: Mapped[float] = mapped_column(Float)
    # Píxeles del fotograma original
    x1: Mapped[int] = mapped_column(Integer)
    y1: Mapped[int] = mapped_column(Integer)
    x2: Mapped[int] = mapped_column(Integer)
    y2: Mapped[int] = mapped_column(Integer)
    recorte_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("recorte.id"))


class Fotograma(Base):
    """Fotograma analizado de una sesión en vivo, tenga detecciones o no.

    En el modo en vivo los fotogramas no llegan a intervalos fijos, así que el informe
    necesita el segundo de cada uno para saber cuánto tiempo representa.
    """

    __tablename__ = "fotograma"
    __table_args__ = (Index("ix_fotograma_analisis_id_t_s", "analisis_id", "t_s"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analisis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("analisis.id", ondelete="CASCADE")
    )
    t_s: Mapped[float] = mapped_column(Float)  # segundo del vídeo
