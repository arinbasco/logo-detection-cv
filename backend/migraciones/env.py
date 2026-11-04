"""Entorno de Alembic. Lee la cadena de conexión de DATABASE_URL, nunca de alembic.ini."""

from logging.config import fileConfig

from alembic import context

from basedatos import crear_motor, normalizar_url
from config import url_base_datos
from modelos import Base

configuracion = context.config
if configuracion.config_file_name and configuracion.attributes.get("configurar_registros", True):
    fileConfig(configuracion.config_file_name, disable_existing_loggers=False)

metadatos = Base.metadata


def migrar_sin_conexion() -> None:
    """Genera el SQL de las migraciones sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=normalizar_url(url_base_datos()),
        target_metadata=metadatos,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def migrar_con_conexion() -> None:
    motor = crear_motor(url_base_datos())
    try:
        with motor.connect() as conexion:
            es_sqlite = conexion.dialect.name == "sqlite"
            if es_sqlite:
                # Al recrear una tabla por lotes, SQLite la borra y, con las claves ajenas
                # activas, borraría en cascada las filas que la referencian. Se desactivan
                # mientras dura la migración; fuera de una transacción, o no tendría efecto.
                conexion.exec_driver_sql("PRAGMA foreign_keys=OFF")
                conexion.commit()
            # SQLite no puede modificar columnas en sitio: Alembic recrea la tabla por lotes
            context.configure(
                connection=conexion,
                target_metadata=metadatos,
                render_as_batch=es_sqlite,
            )
            with context.begin_transaction():
                context.run_migrations()
                if es_sqlite and conexion.exec_driver_sql("PRAGMA foreign_key_check").first():
                    raise RuntimeError("La migración ha dejado filas que apuntan a otras que no existen")
    finally:
        motor.dispose()


if context.is_offline_mode():
    migrar_sin_conexion()
else:
    migrar_con_conexion()
