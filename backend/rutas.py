"""Endpoints del modo informe y de consulta."""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, BinaryIO

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import informe
import videos
from cliente_modelo import ClienteModelo, ErrorModelo
from config import Ajustes
from esquemas import (
    AnalisisCreado,
    Configuracion,
    DeteccionGuardada,
    EstadoAnalisis,
    Informe,
    Salud,
    errores,
)
from modelos import Analisis, Deteccion, Fotograma, Recorte, ahora_utc
from procesamiento import GestorAnalisis
from seguridad import ANALISIS_EN_CURSO, MAX_BYTES_VIDEO, VIDEO_GRANDE

NO_ENCONTRADO = "No encontrado."
SIN_TERMINAR = "El análisis todavía no ha terminado."
SIN_RESULTADOS = "El análisis falló y no tiene resultados."
FORMATO_VIDEO = "Formato no admitido. Solo se aceptan vídeos MP4, MOV, WEBM y AVI."
MODELO_NO_RESPONDE = "La API del modelo no responde."
TAMANO_TROZO = 1024 * 1024

# Descripciones de las respuestas de error en el OpenAPI
ANALISIS_INEXISTENTE = "No existe ningún análisis con ese identificador."
ANALISIS_SIN_RESULTADOS = "El análisis todavía no ha terminado, o falló y no tiene resultados."


@dataclass
class Contexto:
    """Piezas compartidas por los endpoints, creadas una sola vez al arrancar."""

    ajustes: Ajustes
    sesiones: sessionmaker[Session]
    cliente: ClienteModelo
    gestor: GestorAnalisis


def obtener_contexto(request: Request) -> Contexto:
    return request.app.state.contexto


class ArchivoDemasiadoGrande(Exception):
    pass


def uuid_o_404(texto: str) -> uuid.UUID:
    """Convierte el identificador. Uno mal formado responde igual que uno que no existe."""
    try:
        return uuid.UUID(texto)
    except ValueError:
        raise HTTPException(status_code=404, detail=NO_ENCONTRADO) from None


def _buscar_analisis(sesion: Session, texto: str) -> Analisis:
    analisis = sesion.get(Analisis, uuid_o_404(texto))
    if analisis is None:
        raise HTTPException(status_code=404, detail=NO_ENCONTRADO)
    return analisis


def _exigir_completado(analisis: Analisis) -> None:
    if analisis.estado == "fallido":
        raise HTTPException(status_code=409, detail=SIN_RESULTADOS)
    if analisis.estado != "completado":
        raise HTTPException(status_code=409, detail=SIN_TERMINAR)


def nombre_para_mostrar(nombre: str | None) -> str:
    """Nombre original del archivo, sin carpetas ni caracteres de control, de 255 como máximo."""
    nombre = (nombre or "").replace("\\", "/").rsplit("/", 1)[-1]
    nombre = "".join(c for c in nombre if c.isprintable()).strip()
    return nombre[:255] or "video"


def _guardar_por_trozos(origen: BinaryIO, destino: Path, maximo: int) -> None:
    """Copia la subida al archivo temporal por trozos y corta en cuanto supera el máximo."""
    escritos = 0
    with open(destino, "xb") as salida:
        while trozo := origen.read(TAMANO_TROZO):
            escritos += len(trozo)
            if escritos > maximo:
                raise ArchivoDemasiadoGrande
            salida.write(trozo)


def _descartar(ctx: Contexto, ruta: Path | None) -> None:
    """Deshace una subida rechazada: borra el temporal y libera el hueco del análisis."""
    if ruta is not None:
        ruta.unlink(missing_ok=True)
    ctx.gestor.liberar()


def _tiempo_restante(analisis: Analisis, segundos_por_fotograma: float) -> float:
    # En el modo en vivo el ritmo lo marca la reproducción, así que no hay estimación
    if analisis.modo == "en_vivo" or analisis.estado not in ("en_cola", "procesando"):
        return 0.0
    total = videos.numero_de_muestras(analisis.duracion_s, analisis.intervalo_s)
    procesados = round(analisis.progreso * total)
    return round(max(total - procesados, 0) * segundos_por_fotograma, 1)


def describir_estado(analisis: Analisis, segundos_por_fotograma: float) -> dict:
    """Cuerpo de GET /analisis/{id}, que devuelve también el cierre de una sesión en vivo."""
    return {
        "id": analisis.id,
        "nombre_video": analisis.nombre_video,
        "modo": analisis.modo,
        "estado": analisis.estado,
        "progreso": round(analisis.progreso, 4),
        "duracion_s": analisis.duracion_s,
        "fps": analisis.fps,
        "intervalo_s": analisis.intervalo_s,
        "umbral": analisis.umbral,
        "creado": analisis.creado,
        "error": analisis.error,
        "tiempo_restante_s": _tiempo_restante(analisis, segundos_por_fotograma),
    }


def registrar_rutas(app: FastAPI) -> None:
    """Registra los endpoints directamente en la app, para que slowapi encuentre cada ruta."""
    ContextoDep = Annotated[Contexto, Depends(obtener_contexto)]

    @app.get("/salud", response_model=Salud, responses=errores())
    def salud() -> dict:
        """Comprueba que el servicio está vivo. Sirve también para despertarlo."""
        return {"estado": "ok"}

    @app.get("/config", response_model=Configuracion, responses=errores())
    def configuracion(ctx: ContextoDep) -> dict:
        """Modos activos y segundos que tarda de media cada fotograma en la API del modelo."""
        return {"modos": list(ctx.ajustes.modos), "segundos_por_fotograma": round(ctx.cliente.media.valor(), 2)}

    @app.get("/marcas", response_model=list[str], responses=errores({502: MODELO_NO_RESPONDE}))
    def marcas(ctx: ContextoDep) -> list[str]:
        """Las marcas que reconoce el modelo."""
        try:
            return ctx.cliente.marcas()
        except ErrorModelo:
            raise HTTPException(status_code=502, detail=MODELO_NO_RESPONDE) from None

    @app.post("/analisis", status_code=202, response_model=AnalisisCreado, responses=errores({
        413: VIDEO_GRANDE,
        415: "El archivo no es un vídeo MP4, MOV, WEBM o AVI que se pueda leer.",
        422: "Parámetros fuera de rango, o un vídeo que supera la duración o la resolución máximas.",
        429: "Demasiadas peticiones seguidas desde la misma IP, o ya hay un análisis en curso.",
    }))
    def crear_analisis(
        video: Annotated[UploadFile, File(description="Vídeo MP4, MOV, WEBM o AVI")],
        ctx: ContextoDep,
        intervalo_s: Annotated[float, Form(ge=0.5, le=5.0, allow_inf_nan=False)] = 1.0,
        umbral: Annotated[float, Form(ge=0.05, le=0.95, allow_inf_nan=False)] = 0.775,
    ) -> dict:
        """Recibe un vídeo, lo valida y lanza su análisis en segundo plano."""
        if not ctx.gestor.reservar():
            raise HTTPException(status_code=429, detail=ANALISIS_EN_CURSO)
        ruta: Path | None = None
        try:
            nombre = nombre_para_mostrar(video.filename)
            extension = Path(nombre).suffix.lower()
            if extension not in videos.EXTENSIONES:
                raise HTTPException(status_code=415, detail=FORMATO_VIDEO)
            # El temporal se llama con un UUID: el nombre del usuario nunca se usa como ruta
            ruta = ctx.gestor.carpeta_temporal / f"{uuid.uuid4()}{extension}"
            _guardar_por_trozos(video.file, ruta, MAX_BYTES_VIDEO)
            info = videos.inspeccionar(ruta)
            analisis = Analisis(
                id=uuid.uuid4(), nombre_video=nombre, modo="informe", estado="en_cola", progreso=0.0,
                duracion_s=info.duracion_s, fps=round(info.fps, 3), intervalo_s=intervalo_s,
                umbral=umbral, fotogramas_analizados=0, creado=ahora_utc(),
            )
            with ctx.sesiones() as sesion:
                sesion.add(analisis)
                sesion.commit()
            ctx.gestor.lanzar(analisis.id, ruta, info, intervalo_s, umbral)
        except ArchivoDemasiadoGrande:
            _descartar(ctx, ruta)
            raise HTTPException(status_code=413, detail=VIDEO_GRANDE) from None
        except videos.VideoNoAdmitido:
            _descartar(ctx, ruta)
            raise HTTPException(status_code=415, detail=FORMATO_VIDEO) from None
        except videos.VideoFueraDeLimites as error:
            _descartar(ctx, ruta)
            raise HTTPException(status_code=422, detail=str(error)) from None
        except BaseException:
            _descartar(ctx, ruta)
            raise
        total = videos.numero_de_muestras(info.duracion_s, intervalo_s)
        return {
            "id": analisis.id,
            "estado": "en_cola",
            "tiempo_estimado_s": round(total * ctx.cliente.media.valor(), 1),
        }

    @app.get("/analisis/{analisis_id}", response_model=EstadoAnalisis, responses=errores({404: ANALISIS_INEXISTENTE}))
    def estado_analisis(analisis_id: str, ctx: ContextoDep) -> dict:
        """Estado y progreso de un análisis o de una sesión en vivo."""
        with ctx.sesiones() as sesion:
            analisis = _buscar_analisis(sesion, analisis_id)
        return describir_estado(analisis, ctx.cliente.media.valor())

    @app.get("/analisis/{analisis_id}/informe", response_model=Informe, responses=errores({
        404: ANALISIS_INEXISTENTE, 409: ANALISIS_SIN_RESULTADOS,
    }))
    def informe_analisis(analisis_id: str, ctx: ContextoDep) -> dict:
        """Tiempo en pantalla por marca, con el resumen redactado y los hallazgos que lo justifican."""
        fotogramas = None
        with ctx.sesiones() as sesion:
            analisis = _buscar_analisis(sesion, analisis_id)
            _exigir_completado(analisis)
            filas = sesion.execute(
                select(Deteccion.t_s, Deteccion.marca, Deteccion.confianza)
                .where(Deteccion.analisis_id == analisis.id)
                .order_by(Deteccion.t_s, Deteccion.marca, Deteccion.confianza)
            ).all()
            if analisis.modo == "en_vivo":
                # Sin intervalo fijo, lo que cuenta cada fotograma depende de cuándo llegó el siguiente
                fotogramas = list(sesion.scalars(
                    select(Fotograma.t_s).where(Fotograma.analisis_id == analisis.id).order_by(Fotograma.t_s)
                ))
        return informe.construir_informe(
            duracion_s=analisis.duracion_s,
            intervalo_s=analisis.intervalo_s,
            umbral=analisis.umbral,
            fotogramas_analizados=analisis.fotogramas_analizados,
            detecciones=[(t_s, marca, confianza) for t_s, marca, confianza in filas],
            fotogramas=fotogramas,
        )

    @app.get("/analisis/{analisis_id}/detecciones", response_model=list[DeteccionGuardada], responses=errores({
        404: ANALISIS_INEXISTENTE,
        409: ANALISIS_SIN_RESULTADOS,
        422: "El filtro de marca supera los 100 caracteres.",
    }))
    def detecciones_analisis(
        analisis_id: str,
        ctx: ContextoDep,
        marca: Annotated[str | None, Query(max_length=100)] = None,
    ) -> list[dict]:
        """Detecciones con su segundo exacto, ordenadas por tiempo, para dibujar las cajas."""
        with ctx.sesiones() as sesion:
            analisis = _buscar_analisis(sesion, analisis_id)
            _exigir_completado(analisis)
            consulta = select(Deteccion).where(Deteccion.analisis_id == analisis.id)
            if marca is not None:
                consulta = consulta.where(Deteccion.marca == marca)
            filas = sesion.scalars(consulta.order_by(Deteccion.t_s, Deteccion.confianza.desc(), Deteccion.id)).all()
        return [
            {
                "id": d.id,
                "t_s": d.t_s,
                "marca": d.marca,
                "confianza": d.confianza,
                "caja": [d.x1, d.y1, d.x2, d.y2],
                "recorte_id": d.recorte_id,
            }
            for d in filas
        ]

    @app.get(
        "/recortes/{recorte_id}",
        response_class=Response,
        responses={
            200: {"content": {"image/jpeg": {}}, "description": "Recorte en JPEG"},
            **errores({404: "No existe ningún recorte con ese identificador."}),
        },
    )
    def recorte(recorte_id: str, ctx: ContextoDep) -> Response:
        """Imagen JPEG de la caja de una detección."""
        identificador = uuid_o_404(recorte_id)
        with ctx.sesiones() as sesion:
            datos = sesion.scalar(select(Recorte.datos).where(Recorte.id == identificador))
        if datos is None:
            raise HTTPException(status_code=404, detail=NO_ENCONTRADO)
        return Response(content=datos, media_type="image/jpeg")
