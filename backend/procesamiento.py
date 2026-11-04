"""Análisis de vídeos en segundo plano, de uno en uno, dentro del mismo proceso."""

import logging
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

import imagenes
import videos
from cliente_modelo import ClienteModelo, DeteccionModelo, ErrorModelo
from modelos import Analisis, Deteccion, Fotograma, Recorte, ahora_utc

logger = logging.getLogger("backend.analisis")

FALLOS_SEGUIDOS_MAXIMOS = 3  # fotogramas seguidos sin respuesta antes de dar el análisis por fallido
DIAS_CONSERVACION = 7
TAMANO_LOTE = 500  # identificadores por consulta al borrar, para no superar límites de SQLite

ERROR_SIN_RESPUESTA = "El servicio de detección no respondió. Inténtalo de nuevo más tarde."
ERROR_INTERNO = "No se pudo completar el análisis."
ERROR_REINICIO = "El análisis se interrumpió porque el servidor se reinició."
ERROR_SESION_SIN_CERRAR = "La sesión en vivo no se cerró antes de que el servidor se reiniciara."


class GestorAnalisis:
    """Lanza cada análisis en un hilo aparte y garantiza que solo haya uno en curso."""

    def __init__(self, sesiones: sessionmaker[Session], cliente: ClienteModelo, carpeta_temporal: Path):
        self._sesiones = sesiones
        self._cliente = cliente
        self.carpeta_temporal = carpeta_temporal
        self._candado = threading.Lock()
        self._ocupado = False
        self._hilo: threading.Thread | None = None

    @property
    def ocupado(self) -> bool:
        return self._ocupado

    def reservar(self) -> bool:
        """Ocupa el hueco del único análisis permitido. Devuelve False si ya estaba ocupado."""
        with self._candado:
            if self._ocupado:
                return False
            self._ocupado = True
            return True

    def liberar(self) -> None:
        with self._candado:
            self._ocupado = False

    def lanzar(
        self, analisis_id: uuid.UUID, ruta: Path, info: videos.InfoVideo, intervalo_s: float, umbral: float
    ) -> None:
        """Arranca el análisis en otro hilo. El hilo se encarga de borrar el vídeo y liberar el hueco."""
        self._hilo = threading.Thread(
            target=self._ejecutar,
            args=(analisis_id, ruta, info, intervalo_s, umbral),
            name="analisis",
            daemon=True,
        )
        self._hilo.start()

    def esperar(self, segundos: float | None = None) -> bool:
        """Espera a que termine el análisis en curso. Devuelve True si ha terminado."""
        hilo = self._hilo
        if hilo is None:
            return True
        hilo.join(segundos)
        return not hilo.is_alive()

    def _ejecutar(
        self, analisis_id: uuid.UUID, ruta: Path, info: videos.InfoVideo, intervalo_s: float, umbral: float
    ) -> None:
        try:
            self._procesar(analisis_id, ruta, info, intervalo_s, umbral)
        except Exception:
            logger.exception("Error inesperado durante un análisis")
            try:
                self._terminar(analisis_id, "fallido", ERROR_INTERNO)
            except Exception:
                logger.exception("No se pudo marcar el análisis como fallido")
        finally:
            ruta.unlink(missing_ok=True)  # el vídeo temporal se borra siempre, también si falla
            self.liberar()

    def _procesar(
        self, analisis_id: uuid.UUID, ruta: Path, info: videos.InfoVideo, intervalo_s: float, umbral: float
    ) -> None:
        total = videos.numero_de_muestras(info.duracion_s, intervalo_s)
        self._actualizar(analisis_id, estado="procesando")
        procesados = analizados = fallos_seguidos = 0
        for _, t_s, fotograma in videos.muestrear(ruta, info, intervalo_s):
            reducido, factor_x, factor_y = imagenes.reducir(fotograma, imagenes.LADO_MODELO)
            procesados += 1
            try:
                detecciones = self._cliente.predecir(imagenes.codificar_jpeg(reducido), umbral)
            except ErrorModelo:
                # El fotograma queda sin analizar y no cuenta en el informe
                fallos_seguidos += 1
                if fallos_seguidos >= FALLOS_SEGUIDOS_MAXIMOS:
                    self._terminar(analisis_id, "fallido", ERROR_SIN_RESPUESTA, progreso=procesados / total)
                    return
                self._actualizar(analisis_id, progreso=procesados / total)
                continue
            fallos_seguidos = 0
            analizados += 1
            self._guardar(analisis_id, t_s, fotograma, detecciones, (factor_x, factor_y), procesados / total, analizados)

        if procesados == 0:
            self._terminar(analisis_id, "fallido", ERROR_INTERNO)
        elif analizados == 0:
            self._terminar(analisis_id, "fallido", ERROR_SIN_RESPUESTA)
        else:
            self._terminar(analisis_id, "completado", None, progreso=1.0)

    def _guardar(
        self,
        analisis_id: uuid.UUID,
        t_s: float,
        fotograma: np.ndarray,
        detecciones: list[DeteccionModelo],
        factores: tuple[float, float],
        progreso: float,
        analizados: int,
    ) -> None:
        """Guarda las detecciones de un fotograma, con sus recortes, y el progreso, todo junto."""
        with self._sesiones() as sesion:
            anadir_detecciones(sesion, analisis_id, t_s, fotograma, detecciones, factores)
            sesion.execute(
                update(Analisis)
                .where(Analisis.id == analisis_id)
                .values(progreso=progreso, fotogramas_analizados=analizados)
            )
            sesion.commit()

    def _actualizar(self, analisis_id: uuid.UUID, **valores) -> None:
        with self._sesiones() as sesion:
            sesion.execute(update(Analisis).where(Analisis.id == analisis_id).values(**valores))
            sesion.commit()

    def _terminar(self, analisis_id: uuid.UUID, estado: str, error: str | None, **valores) -> None:
        self._actualizar(analisis_id, estado=estado, error=error, terminado=ahora_utc(), **valores)


def anadir_detecciones(
    sesion: Session,
    analisis_id: uuid.UUID,
    t_s: float,
    fotograma: np.ndarray,
    detecciones: list[DeteccionModelo],
    factores: tuple[float, float],
) -> None:
    """Añade a la sesión las detecciones de un fotograma con sus recortes, sin confirmar.

    Las cajas de la API del modelo vienen en píxeles de la imagen reducida y se guardan en
    píxeles del fotograma original, del que sale también el recorte.
    """
    alto, ancho = fotograma.shape[:2]
    recortes, filas = [], []
    for d in detecciones:
        caja = imagenes.a_original(d.caja, factores[0], factores[1], ancho, alto)
        x1, y1, x2, y2 = (round(valor) for valor in caja)
        recorte = Recorte(id=uuid.uuid4(), datos=imagenes.recortar(fotograma, x1, y1, x2, y2))
        recortes.append(recorte)
        filas.append(Deteccion(
            id=uuid.uuid4(), analisis_id=analisis_id, t_s=t_s, marca=d.marca, confianza=d.confianza,
            x1=x1, y1=y1, x2=x2, y2=y2, recorte_id=recorte.id,
        ))
    sesion.add_all(recortes)
    sesion.flush()  # los recortes primero, porque las detecciones los referencian
    sesion.add_all(filas)


def _lotes(identificadores: list[uuid.UUID]) -> Iterator[list[uuid.UUID]]:
    for inicio in range(0, len(identificadores), TAMANO_LOTE):
        yield identificadores[inicio:inicio + TAMANO_LOTE]


def recuperar_tras_reinicio(sesiones: sessionmaker[Session]) -> int:
    """Marca como fallidos los análisis que un reinicio dejó a medias y las sesiones en vivo sin cerrar."""
    total = 0
    with sesiones() as sesion:
        for modo, error in (("informe", ERROR_REINICIO), ("en_vivo", ERROR_SESION_SIN_CERRAR)):
            resultado = sesion.execute(
                update(Analisis)
                .where(Analisis.modo == modo, Analisis.estado.in_(("en_cola", "procesando")))
                .values(estado="fallido", error=error, terminado=ahora_utc())
            )
            total += resultado.rowcount
        sesion.commit()
    return total


def borrar_antiguos(sesiones: sessionmaker[Session], ahora: datetime | None = None) -> int:
    """Borra los análisis de más de 7 días con sus detecciones, sus recortes y sus fotogramas."""
    limite = (ahora or ahora_utc()) - timedelta(days=DIAS_CONSERVACION)
    with sesiones() as sesion:
        antiguos = list(sesion.scalars(select(Analisis.id).where(Analisis.creado < limite)))
        for lote in _lotes(antiguos):
            recortes = list(sesion.scalars(select(Deteccion.recorte_id).where(Deteccion.analisis_id.in_(lote))))
            sesion.execute(delete(Deteccion).where(Deteccion.analisis_id.in_(lote)))
            for lote_recortes in _lotes(recortes):
                sesion.execute(delete(Recorte).where(Recorte.id.in_(lote_recortes)))
            sesion.execute(delete(Fotograma).where(Fotograma.analisis_id.in_(lote)))
            sesion.execute(delete(Analisis).where(Analisis.id.in_(lote)))
        sesion.commit()
        return len(antiguos)


def limpiar_temporales(carpeta: Path) -> None:
    """Borra los vídeos temporales que pudiera haber dejado un reinicio."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for archivo in carpeta.iterdir():
        if archivo.is_file():
            archivo.unlink(missing_ok=True)
