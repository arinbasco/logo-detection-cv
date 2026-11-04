"""Conexión a la base de datos: Postgres en Render y SQLite en local, con el mismo código."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from config import CARPETA_BACKEND


def normalizar_url(texto: str) -> URL:
    """Ajusta la cadena de conexión para que funcione igual en Render y en local.

    Render da direcciones postgres:// o postgresql://, que SQLAlchemy asocia a psycopg2,
    así que se fuerza psycopg 3. Las rutas relativas de SQLite se resuelven desde la
    carpeta backend, para no depender de la carpeta desde la que se arranca.
    """
    url = make_url(texto)
    if url.drivername in ("postgres", "postgresql"):
        return url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        ruta = Path(url.database)
        if not ruta.is_absolute():
            return url.set(database=str(CARPETA_BACKEND / ruta))
    return url


def crear_motor(texto: str) -> Engine:
    """Crea el motor de SQLAlchemy. Los errores nunca muestran los valores de la consulta."""
    url = normalizar_url(texto)
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True, hide_parameters=True)

    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    # El análisis corre en otro hilo, así que la conexión no puede atarse a un solo hilo
    motor = create_engine(url, connect_args={"check_same_thread": False}, hide_parameters=True)

    @event.listens_for(motor, "connect")
    def _configurar_sqlite(conexion, _registro) -> None:
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")  # SQLite no aplica el borrado en cascada sin esto
        cursor.execute("PRAGMA journal_mode=WAL")  # lecturas sin bloquear mientras se escribe
        cursor.close()

    return motor


def crear_sesiones(motor: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=motor, expire_on_commit=False)
