/** Comprobaciones del vídeo en el navegador, antes de llamar al backend. */

export const EXTENSIONES = [".mp4", ".mov", ".webm", ".avi"]
export const TIPOS_ACEPTADOS = "video/mp4,video/quicktime,video/webm,video/x-msvideo,.mp4,.mov,.webm,.avi"
export const MAX_BYTES_VIDEO = 100 * 1024 * 1024
export const DURACION_MAXIMA_S = 120

// Los mismos textos que da el backend, para que el usuario lea lo mismo lo detecte quien lo detecte
export const FORMATO_NO_ADMITIDO = "Formato no admitido. Solo se aceptan vídeos MP4, MOV, WEBM y AVI."
export const VIDEO_GRANDE = "El vídeo supera los 100 MB."
export const VIDEO_LARGO = "El vídeo no puede durar más de 2 minutos."

export type Comprobacion = { valido: true; duracion: number | null } | { valido: false; mensaje: string }

/**
 * Duración del vídeo leída de sus metadatos, o null si el navegador no sabe leerlo, como
 * pasa con los AVI. En ese caso la comprobará el backend.
 */
export function leerDuracion(archivo: File): Promise<number | null> {
  return new Promise((resolver) => {
    const video = document.createElement("video")
    const url = URL.createObjectURL(archivo)
    const terminar = (duracion: number | null) => {
      clearTimeout(limite)
      video.removeAttribute("src")
      video.load()
      URL.revokeObjectURL(url)
      resolver(duracion)
    }
    const limite = setTimeout(() => terminar(null), 10_000)
    video.preload = "metadata"
    video.muted = true
    video.onloadedmetadata = () => terminar(Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null)
    video.onerror = () => terminar(null)
    video.src = url
  })
}

/** Formato, tamaño y duración, con el propio archivo y sin llamar al backend. */
export async function comprobarVideo(archivo: File): Promise<Comprobacion> {
  const punto = archivo.name.lastIndexOf(".")
  const extension = punto >= 0 ? archivo.name.slice(punto).toLowerCase() : ""
  if (!EXTENSIONES.includes(extension)) return { valido: false, mensaje: FORMATO_NO_ADMITIDO }
  if (archivo.size > MAX_BYTES_VIDEO) return { valido: false, mensaje: VIDEO_GRANDE }
  const duracion = await leerDuracion(archivo)
  if (duracion !== null && duracion > DURACION_MAXIMA_S) return { valido: false, mensaje: VIDEO_LARGO }
  return { valido: true, duracion }
}

/** Fotogramas que analiza el backend: uno cada intervalo_s segundos desde el segundo 0. */
export function numeroDeMuestras(duracion_s: number, intervalo_s: number): number {
  return Math.max(1, Math.ceil(Math.round((duracion_s / intervalo_s) * 1e6) / 1e6))
}
