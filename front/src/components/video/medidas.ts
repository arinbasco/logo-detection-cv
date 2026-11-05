/** Medidas del vídeo en pantalla y sincronización de las cajas con el tiempo del vídeo. */

import { useEffect, useMemo, useState } from "react"

import { areaVisible, grupoEn, type Grupo, type Tamano } from "@/lib/cajas"

interface Medidas {
  contenedor: Tamano // tamaño del elemento <video> en pantalla
  video: Tamano // tamaño de la imagen, videoWidth y videoHeight
}

const VACIO: Medidas = { contenedor: { ancho: 0, alto: 0 }, video: { ancho: 0, alto: 0 } }

function iguales(a: Medidas, b: Medidas): boolean {
  return (
    a.contenedor.ancho === b.contenedor.ancho &&
    a.contenedor.alto === b.contenedor.alto &&
    a.video.ancho === b.video.ancho &&
    a.video.alto === b.video.alto
  )
}

/** Tamaño del vídeo y zona visible de la imagen. Se recalcula al cambiar el tamaño de la ventana. */
export function useAreaVideo(video: HTMLVideoElement | null) {
  const [medidas, setMedidas] = useState<Medidas>(VACIO)

  useEffect(() => {
    if (!video) return
    const medir = () => {
      const nuevas = {
        contenedor: { ancho: video.clientWidth, alto: video.clientHeight },
        video: { ancho: video.videoWidth, alto: video.videoHeight },
      }
      setMedidas((anteriores) => (iguales(anteriores, nuevas) ? anteriores : nuevas))
    }
    const observador = new ResizeObserver(medir)
    observador.observe(video)
    video.addEventListener("loadedmetadata", medir)
    video.addEventListener("resize", medir) // cambia videoWidth, por ejemplo al elegir otro archivo
    medir()
    return () => {
      observador.disconnect()
      video.removeEventListener("loadedmetadata", medir)
      video.removeEventListener("resize", medir)
    }
  }, [video])

  const area = useMemo(() => areaVisible(medidas.contenedor, medidas.video), [medidas])
  return { ...medidas, area }
}

/**
 * Índice del grupo de detecciones que toca mostrar en cada momento del vídeo.
 *
 * Se comprueba en cada fotograma con requestVideoFrameCallback, o con requestAnimationFrame
 * si el navegador no lo tiene. Solo provoca un nuevo render cuando cambia el grupo.
 */
export function useGrupoActivo(video: HTMLVideoElement | null, grupos: Grupo[]): number {
  const [indice, setIndice] = useState(-1)

  useEffect(() => {
    if (!video) return
    const actualizar = () => {
      const nuevo = grupoEn(grupos, video.currentTime)
      setIndice((anterior) => (anterior === nuevo ? anterior : nuevo))
    }
    let activo = true
    let marca = 0
    const conFotogramas = typeof video.requestVideoFrameCallback === "function"
    if (conFotogramas) {
      const paso = () => {
        if (!activo) return
        actualizar()
        marca = video.requestVideoFrameCallback(paso)
      }
      marca = video.requestVideoFrameCallback(paso)
    } else {
      const paso = () => {
        if (!activo) return
        actualizar()
        marca = requestAnimationFrame(paso)
      }
      marca = requestAnimationFrame(paso)
    }
    // Al saltar con el vídeo en pausa también hay que actualizar las cajas
    video.addEventListener("seeked", actualizar)
    video.addEventListener("loadeddata", actualizar)
    actualizar()
    return () => {
      activo = false
      if (conFotogramas) video.cancelVideoFrameCallback(marca)
      else cancelAnimationFrame(marca)
      video.removeEventListener("seeked", actualizar)
      video.removeEventListener("loadeddata", actualizar)
    }
  }, [video, grupos])

  return indice
}
