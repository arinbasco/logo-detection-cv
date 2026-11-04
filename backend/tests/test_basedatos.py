"""Migraciones y tareas de arranque: análisis interrumpidos, borrado de antiguos y temporales."""

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from basedatos import crear_motor, crear_sesiones
from config import CARPETA_BACKEND
from modelos import Analisis, Base, Deteccion, FechaUTC, Fotograma, Recorte, ahora_utc
from procesamiento import ERROR_REINICIO, ERROR_SESION_SIN_CERRAR


def _analisis(estado: str, creado, modo: str = "informe") -> Analisis:
    en_vivo = modo == "en_vivo"
    return Analisis(
        id=uuid.uuid4(), nombre_video="v.mp4", modo=modo, estado=estado, progreso=0.0, duracion_s=10.0,
        fps=None if en_vivo else 10.0, intervalo_s=None if en_vivo else 1.0, umbral=0.775,
        fotogramas_analizados=0, creado=creado,
    )


def _alembic() -> Config:
    configuracion = Config(str(CARPETA_BACKEND / "alembic.ini"))
    configuracion.attributes["configurar_registros"] = False
    return configuracion


def test_la_migracion_coincide_con_los_modelos(url_bd):
    motor = crear_motor(url_bd)
    with motor.connect() as conexion:
        diferencias = compare_metadata(MigrationContext.configure(conexion), Base.metadata)
    motor.dispose()
    assert diferencias == []


def test_al_arrancar_marca_interrumpidos_y_borra_lo_antiguo(url_bd, crear_cliente, carpeta_temporal):
    motor = crear_motor(url_bd)
    sesiones = crear_sesiones(motor)
    ahora = ahora_utc()
    en_cola, procesando = _analisis("en_cola", ahora), _analisis("procesando", ahora)
    sin_cerrar = _analisis("procesando", ahora, modo="en_vivo")
    cerrada = _analisis("completado", ahora, modo="en_vivo")
    reciente = _analisis("completado", ahora - timedelta(days=6))
    antiguo = _analisis("completado", ahora - timedelta(days=8))
    sesion_antigua = _analisis("completado", ahora - timedelta(days=8), modo="en_vivo")
    recorte_antiguo = Recorte(id=uuid.uuid4(), datos=b"jpeg")
    with sesiones() as sesion:
        sesion.add_all([en_cola, procesando, sin_cerrar, cerrada, reciente, antiguo, sesion_antigua, recorte_antiguo])
        sesion.flush()
        sesion.add(Deteccion(
            id=uuid.uuid4(), analisis_id=antiguo.id, t_s=0.0, marca="Nike", confianza=0.9,
            x1=0, y1=0, x2=10, y2=10, recorte_id=recorte_antiguo.id,
        ))
        sesion.add_all([
            Fotograma(id=uuid.uuid4(), analisis_id=sesion_antigua.id, t_s=0.0),
            Fotograma(id=uuid.uuid4(), analisis_id=cerrada.id, t_s=0.0),
        ])
        sesion.commit()
    carpeta_temporal.mkdir(parents=True)
    (carpeta_temporal / "resto_de_un_reinicio.mp4").write_bytes(b"video")

    crear_cliente()  # arrancar la app ejecuta las tareas de arranque

    with sesiones() as sesion:
        for interrumpido, error in ((en_cola, ERROR_REINICIO), (procesando, ERROR_REINICIO),
                                    (sin_cerrar, ERROR_SESION_SIN_CERRAR)):
            fila = sesion.get(Analisis, interrumpido.id)
            assert fila.estado == "fallido"
            assert fila.error == error
            assert fila.terminado is not None
        assert sesion.get(Analisis, reciente.id).estado == "completado"
        assert sesion.get(Analisis, cerrada.id).estado == "completado"
        assert sesion.get(Analisis, antiguo.id) is None
        assert sesion.get(Analisis, sesion_antigua.id) is None
        assert sesion.get(Recorte, recorte_antiguo.id) is None
        assert sesion.scalar(select(func.count()).select_from(Deteccion)) == 0
        # Solo queda el fotograma de la sesión reciente
        assert list(sesion.scalars(select(Fotograma.analisis_id))) == [cerrada.id]
    assert list(carpeta_temporal.iterdir()) == []
    motor.dispose()


# Tablas tal como las deja la migración 0001, para escribir en ellas sin los modelos actuales
ANALISIS_0001 = sa.table(
    "analisis", sa.column("id", sa.Uuid()), sa.column("nombre_video"), sa.column("estado"),
    sa.column("progreso"), sa.column("duracion_s"), sa.column("fps"), sa.column("intervalo_s"),
    sa.column("umbral"), sa.column("fotogramas_analizados"), sa.column("creado", FechaUTC()),
)
RECORTE_0001 = sa.table("recorte", sa.column("id", sa.Uuid()), sa.column("datos", sa.LargeBinary()))
DETECCION_0001 = sa.table(
    "deteccion", sa.column("id", sa.Uuid()), sa.column("analisis_id", sa.Uuid()), sa.column("t_s"),
    sa.column("marca"), sa.column("confianza"), sa.column("x1"), sa.column("y1"), sa.column("x2"),
    sa.column("y2"), sa.column("recorte_id", sa.Uuid()),
)


@pytest.fixture
def url_bd_0001(tmp_path, monkeypatch) -> str:
    """Base de datos SQLite temporal con solo la migración 0001 aplicada."""
    url = f"sqlite:///{(tmp_path / 'antigua.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_alembic(), "0001")
    return url


def test_la_migracion_0002_conserva_los_datos_y_los_marca_como_informe(url_bd_0001):
    motor = crear_motor(url_bd_0001)
    analisis_id, recorte_id = uuid.uuid4(), uuid.uuid4()
    with motor.begin() as conexion:
        conexion.execute(ANALISIS_0001.insert().values(
            id=analisis_id, nombre_video="v.mp4", estado="completado", progreso=1.0, duracion_s=10.0,
            fps=25.0, intervalo_s=1.0, umbral=0.775, fotogramas_analizados=10, creado=ahora_utc(),
        ))
        conexion.execute(RECORTE_0001.insert().values(id=recorte_id, datos=b"jpeg"))
        conexion.execute(DETECCION_0001.insert().values(
            id=uuid.uuid4(), analisis_id=analisis_id, t_s=0.0, marca="Nike", confianza=0.9,
            x1=0, y1=0, x2=10, y2=10, recorte_id=recorte_id,
        ))
    motor.dispose()

    command.upgrade(_alembic(), "head")

    motor = crear_motor(url_bd_0001)
    sesiones = crear_sesiones(motor)
    with sesiones() as sesion:
        fila = sesion.get(Analisis, analisis_id)
        assert (fila.modo, fila.fps, fila.intervalo_s, fila.fotogramas_analizados) == ("informe", 25.0, 1.0, 10)
        # Recrear la tabla no puede borrar en cascada las detecciones que la referencian
        assert sesion.scalar(select(func.count()).select_from(Deteccion)) == 1
        assert sesion.get(Recorte, recorte_id) is not None
        sesion.add(_analisis("procesando", ahora_utc(), modo="en_vivo"))  # sin fps ni intervalo
        sesion.commit()
    # Las restricciones de estado y de modo siguen en la tabla nueva
    for cambio in ({"estado": "raro"}, {"modo": "otro"}):
        with sesiones() as sesion:
            fila = _analisis("completado", ahora_utc())
            for campo, valor in cambio.items():
                setattr(fila, campo, valor)
            sesion.add(fila)
            with pytest.raises(IntegrityError):
                sesion.commit()
    motor.dispose()


def test_la_migracion_0002_se_puede_deshacer(url_bd):
    motor = crear_motor(url_bd)
    sesiones = crear_sesiones(motor)
    informe, en_vivo = _analisis("completado", ahora_utc()), _analisis("completado", ahora_utc(), modo="en_vivo")
    recortes = [Recorte(id=uuid.uuid4(), datos=b"jpeg") for _ in range(2)]
    with sesiones() as sesion:
        sesion.add_all([informe, en_vivo, *recortes])
        sesion.flush()
        for analisis, recorte in zip((informe, en_vivo), recortes):
            sesion.add(Deteccion(
                id=uuid.uuid4(), analisis_id=analisis.id, t_s=0.0, marca="Nike", confianza=0.9,
                x1=0, y1=0, x2=10, y2=10, recorte_id=recorte.id,
            ))
        sesion.add(Fotograma(id=uuid.uuid4(), analisis_id=en_vivo.id, t_s=0.0))
        sesion.commit()
    motor.dispose()

    command.downgrade(_alembic(), "0001")

    motor = crear_motor(url_bd)
    with motor.connect() as conexion:
        assert "fotograma" not in sa.inspect(conexion).get_table_names()
        # Las sesiones en vivo se van con sus detecciones y sus recortes; lo demás se queda
        assert conexion.execute(sa.text("SELECT nombre_video FROM analisis")).all() == [("v.mp4",)]
        assert conexion.execute(sa.text("SELECT count(*) FROM deteccion")).scalar() == 1
        assert conexion.execute(sa.text("SELECT count(*) FROM recorte")).scalar() == 1
    motor.dispose()
    command.upgrade(_alembic(), "head")
