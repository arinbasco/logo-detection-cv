"""Modo en vivo: sesiones con los fotogramas que envía el front mientras reproduce un vídeo.

Solo existe si MODOS incluye en_vivo. Cada sesión es un análisis con modo en_vivo que guarda
los fotogramas analizados, con detecciones o sin ellas. Al cerrarla tiene el mismo informe,
las mismas detecciones y los mismos recortes que un análisis del modo informe.
"""

import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from slowapi import Limiter
from sqlalchemy import case, update
from sqlalchemy.orm import Session

import imagenes
import videos
from cliente_modelo import ErrorModelo
from esquemas import EstadoAnalisis, RespuestaEnVivo, SesionCreada, errores
from modelos import Analisis, Fotograma, ahora_utc
from procesamiento import anadir_detecciones
from rutas import (
    MODELO_NO_RESPONDE,
    NO_ENCONTRADO,
    Contexto,
    describir_estado,
    nombre_para_mostrar,
    obtener_contexto,
    uuid_o_404,
)
from seguridad import FOTOGRAMA_GRANDE, MAX_BYTES_FOTOGRAMA

FORMATO_IMAGEN = "Formato no admitido. Solo se aceptan imágenes JPEG y PNG."
IMAGEN_DEMASIADO_GRANDE = "La imagen no puede superar 1920 × 1920 píxeles."
SESION_TERMINADA = "La sesión en vivo ya ha terminado."
SESION_FALLIDA = "La sesión en vivo falló y no se puede cerrar."
SEGUNDO_FUERA_DEL_VIDEO = "El segundo del fotograma no puede superar la duración del vídeo."
ERROR_SIN_FOTOGRAMAS = "No se analizó ningún fotograma."

SESION_INEXISTENTE = "No existe ninguna sesión en vivo con ese identificador."


def _buscar_sesion(sesion: Session, texto: str) -> Analisis:
    """Sesión en vivo por su identificador. Un análisis del modo informe responde como si no existiera."""
    analisis = sesion.get(Analisis, uuid_o_404(texto))
    if analisis is None or analisis.modo != "en_vivo":
        raise HTTPException(status_code=404, detail=NO_ENCONTRADO)
    return analisis


def registrar_rutas_en_vivo(app: FastAPI, limitador: Limiter, peticiones_por_minuto: int) -> None:
    """Registra los endpoints del modo en vivo. El de fotogramas tiene su propio límite por minuto."""
    ContextoDep = Annotated[Contexto, Depends(obtener_contexto)]

    @app.post("/en-vivo/sesion", status_code=201, response_model=SesionCreada, responses=errores({
        422: "Parámetros fuera de rango, o un vídeo de más de 2 minutos.",
    }))
    def crear_sesion(
        ctx: ContextoDep,
        nombre_video: Annotated[str, Form(description="Nombre del archivo, solo para mostrarlo")],
        duracion_s: Annotated[float, Form(gt=0, allow_inf_nan=False)],
        umbral: Annotated[float, Form(ge=0.05, le=0.95, allow_inf_nan=False)] = 0.775,
    ) -> dict:
        """Abre una sesión en vivo para un vídeo que el front va a reproducir."""
        if duracion_s > videos.DURACION_MAXIMA_S:
            raise HTTPException(status_code=422, detail=videos.DEMASIADO_LARGO)
        analisis = Analisis(
            id=uuid.uuid4(), nombre_video=nombre_para_mostrar(nombre_video), modo="en_vivo",
            estado="procesando", progreso=0.0, duracion_s=duracion_s, fps=None, intervalo_s=None,
            umbral=umbral, fotogramas_analizados=0, creado=ahora_utc(),
        )
        with ctx.sesiones() as sesion:
            sesion.add(analisis)
            sesion.commit()
        return {"id": analisis.id}

    @app.post("/en-vivo/fotograma", response_model=RespuestaEnVivo, responses=errores({
        404: SESION_INEXISTENTE,
        409: "La sesión en vivo ya está cerrada o falló.",
        413: "La imagen supera los 2 MB o los 1920 × 1920 píxeles.",
        415: "El archivo no es una imagen JPEG o PNG válida.",
        422: "Parámetros no válidos, o un segundo posterior al final del vídeo.",
        429: "Más fotogramas por minuto de los permitidos desde la misma IP.",
        502: MODELO_NO_RESPONDE,
    }))
    @limitador.limit(f"{peticiones_por_minuto}/minute")
    def fotograma_en_vivo(
        request: Request,
        imagen: Annotated[UploadFile, File(description="Fotograma JPEG o PNG de 2 MB como máximo")],
        sesion_id: Annotated[str, Form(description="Identificador que devolvió POST /en-vivo/sesion")],
        t_s: Annotated[float, Form(ge=0, allow_inf_nan=False)],
    ) -> dict:
        """Analiza un fotograma con el umbral de su sesión, lo guarda y devuelve sus detecciones.

        Las detecciones vuelven con el mismo segundo que se envió. Si la API del modelo no
        responde, el fotograma no se guarda y no cuenta como analizado.
        """
        ctx: Contexto = request.app.state.contexto
        with ctx.sesiones() as sesion:
            analisis = _buscar_sesion(sesion, sesion_id)
        if analisis.estado != "procesando":
            raise HTTPException(status_code=409, detail=SESION_TERMINADA)
        if t_s > analisis.duracion_s:
            raise HTTPException(status_code=422, detail=SEGUNDO_FUERA_DEL_VIDEO)

        datos = imagen.file.read(MAX_BYTES_FOTOGRAMA + 1)
        if len(datos) > MAX_BYTES_FOTOGRAMA:
            raise HTTPException(status_code=413, detail=FOTOGRAMA_GRANDE)
        try:
            fotograma = imagenes.decodificar_fotograma(datos)
        except imagenes.ImagenNoAdmitida:
            raise HTTPException(status_code=415, detail=FORMATO_IMAGEN) from None
        except imagenes.ImagenDemasiadoGrande:
            raise HTTPException(status_code=413, detail=IMAGEN_DEMASIADO_GRANDE) from None

        # Como en el modo informe, a la API del modelo solo llegan 640 píxeles de lado
        reducido, factor_x, factor_y = imagenes.reducir(fotograma, imagenes.LADO_MODELO)
        try:
            detecciones = ctx.cliente.predecir(imagenes.codificar_jpeg(reducido), analisis.umbral)
        except ErrorModelo:
            raise HTTPException(status_code=502, detail=MODELO_NO_RESPONDE) from None

        avance = t_s / analisis.duracion_s
        with ctx.sesiones() as sesion:
            # Solo se guarda si la sesión sigue abierta: pudo cerrarse mientras respondía el modelo
            actualizada = sesion.execute(
                update(Analisis)
                .where(Analisis.id == analisis.id, Analisis.estado == "procesando")
                .values(
                    fotogramas_analizados=Analisis.fotogramas_analizados + 1,
                    progreso=case((Analisis.progreso < avance, avance), else_=Analisis.progreso),
                )
            )
            if actualizada.rowcount != 1:
                raise HTTPException(status_code=409, detail=SESION_TERMINADA)
            sesion.add(Fotograma(id=uuid.uuid4(), analisis_id=analisis.id, t_s=t_s))
            anadir_detecciones(sesion, analisis.id, t_s, fotograma, detecciones, (factor_x, factor_y))
            sesion.commit()

        alto, ancho = fotograma.shape[:2]
        return {
            "t_s": t_s,
            "detecciones": [
                {
                    "marca": d.marca,
                    "confianza": d.confianza,
                    # Las cajas vuelven en píxeles de la imagen que envió el front
                    "caja": [round(v, 1) for v in imagenes.a_original(d.caja, factor_x, factor_y, ancho, alto)],
                }
                for d in detecciones
            ],
        }

    @app.post("/en-vivo/sesion/{sesion_id}/fin", response_model=EstadoAnalisis, responses=errores({
        404: SESION_INEXISTENTE,
        409: "La sesión en vivo falló, por ejemplo porque el servidor se reinició antes de cerrarla.",
    }))
    def cerrar_sesion(sesion_id: str, ctx: ContextoDep) -> dict:
        """Cierra una sesión en vivo, que desde entonces tiene informe, detecciones y recortes.

        Cerrarla otra vez no cambia nada. Si no se analizó ningún fotograma, queda fallida.
        """
        with ctx.sesiones() as sesion:
            analisis = _buscar_sesion(sesion, sesion_id)
            if analisis.estado == "fallido":
                raise HTTPException(status_code=409, detail=SESION_FALLIDA)
            if analisis.estado == "procesando":
                abierta = (Analisis.id == analisis.id, Analisis.estado == "procesando")
                terminado = ahora_utc()
                completada = sesion.execute(
                    update(Analisis)
                    .where(*abierta, Analisis.fotogramas_analizados > 0)
                    .values(estado="completado", progreso=1.0, terminado=terminado)
                )
                if completada.rowcount == 0:
                    sesion.execute(
                        update(Analisis)
                        .where(*abierta)
                        .values(estado="fallido", error=ERROR_SIN_FOTOGRAMAS, terminado=terminado)
                    )
                sesion.commit()
                sesion.refresh(analisis)
        return describir_estado(analisis, ctx.cliente.media.valor())
