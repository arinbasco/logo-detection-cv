/**
 * Comunicación con el backend. El front nunca habla con la API del modelo.
 *
 * Los tipos salen de esquema.ts, generado a partir del openapi.json del backend.
 * Todos los errores llegan como {"detail": "texto"}, con un texto pensado para el usuario.
 */

import type { components } from "./esquema"

type Esquemas = components["schemas"]
export type Configuracion = Esquemas["Configuracion"]
export type AnalisisCreado = Esquemas["AnalisisCreado"]
export type EstadoAnalisis = Esquemas["EstadoAnalisis"]
export type Informe = Esquemas["Informe"]
export type MarcaInforme = Esquemas["MarcaInforme"]
export type Hallazgo = Esquemas["Hallazgo"]
export type DeteccionGuardada = Esquemas["DeteccionGuardada"]
export type RespuestaEnVivo = Esquemas["RespuestaEnVivo"]
export type DeteccionEnVivo = Esquemas["DeteccionEnVivo"]
export type SesionCreada = Esquemas["SesionCreada"]

export const URL_API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8001").replace(/\/+$/, "")

const SIN_CONEXION = "No se puede conectar con el servidor. Comprueba tu conexión."
const POR_CODIGO: Record<number, string> = {
  404: "No encontrado.",
  429: "Demasiadas peticiones. Espera un momento antes de volver a intentarlo.",
  500: "Error interno del servidor.",
  502: "La API del modelo no responde.",
  503: "El servidor no está disponible ahora mismo.",
}

/** Error del backend con su código HTTP. El código 0 indica que no hubo respuesta. */
export class ErrorApi extends Error {
  readonly estado: number

  constructor(estado: number, mensaje: string) {
    super(mensaje)
    this.name = "ErrorApi"
    this.estado = estado
  }

  get sinConexion(): boolean {
    return this.estado === 0
  }
}

async function detalle(respuesta: Response): Promise<string> {
  try {
    const cuerpo: unknown = await respuesta.json()
    if (cuerpo && typeof cuerpo === "object" && "detail" in cuerpo && typeof cuerpo.detail === "string") {
      return cuerpo.detail
    }
  } catch {
    // Sin cuerpo JSON: se usa el mensaje genérico del código
  }
  return POR_CODIGO[respuesta.status] ?? `El servidor respondió con un error ${respuesta.status}.`
}

async function pedir(ruta: string, opciones: RequestInit = {}): Promise<Response> {
  let respuesta: Response
  try {
    respuesta = await fetch(`${URL_API}${ruta}`, opciones)
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ErrorApi(0, SIN_CONEXION)
  }
  if (!respuesta.ok) throw new ErrorApi(respuesta.status, await detalle(respuesta))
  return respuesta
}

async function pedirJson<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  return (await pedir(ruta, opciones)).json() as Promise<T>
}

function formulario(campos: Record<string, string | Blob>, nombreArchivo?: string): FormData {
  const datos = new FormData()
  for (const [clave, valor] of Object.entries(campos)) {
    if (valor instanceof Blob) datos.append(clave, valor, nombreArchivo)
    else datos.append(clave, valor)
  }
  return datos
}

const id = (valor: string) => encodeURIComponent(valor)

export const api = {
  salud: (signal?: AbortSignal) => pedirJson<{ estado: string }>("/salud", { signal }),
  config: (signal?: AbortSignal) => pedirJson<Configuracion>("/config", { signal }),
  marcas: (signal?: AbortSignal) => pedirJson<string[]>("/marcas", { signal }),
  estado: (analisis: string, signal?: AbortSignal) => pedirJson<EstadoAnalisis>(`/analisis/${id(analisis)}`, { signal }),
  informe: (analisis: string, signal?: AbortSignal) =>
    pedirJson<Informe>(`/analisis/${id(analisis)}/informe`, { signal }),
  detecciones: (analisis: string, signal?: AbortSignal) =>
    pedirJson<DeteccionGuardada[]>(`/analisis/${id(analisis)}/detecciones`, { signal }),
  recorte: async (recorte: string, signal?: AbortSignal) => (await pedir(`/recortes/${id(recorte)}`, { signal })).blob(),

  crearSesion: (nombreVideo: string, duracion_s: number) =>
    pedirJson<SesionCreada>("/en-vivo/sesion", {
      method: "POST",
      body: formulario({ nombre_video: nombreVideo, duracion_s: String(duracion_s) }),
    }),
  enviarFotograma: (sesion: string, imagen: Blob, t_s: number, signal?: AbortSignal) =>
    pedirJson<RespuestaEnVivo>("/en-vivo/fotograma", {
      method: "POST",
      body: formulario({ imagen, sesion_id: sesion, t_s: String(t_s) }, "fotograma.jpg"),
      signal,
    }),
  cerrarSesion: (sesion: string) => pedirJson<EstadoAnalisis>(`/en-vivo/sesion/${id(sesion)}/fin`, { method: "POST" }),
}

export interface Subida {
  promesa: Promise<AnalisisCreado>
  cancelar: () => void
}

/**
 * Sube un vídeo a POST /analisis con XMLHttpRequest, que, a diferencia de fetch, informa
 * de cuánto se ha enviado. Se dejan intervalo_s y umbral con sus valores por defecto.
 */
export function subirVideo(archivo: File, alProgreso: (fraccion: number) => void): Subida {
  const peticion = new XMLHttpRequest()
  const promesa = new Promise<AnalisisCreado>((resolver, rechazar) => {
    peticion.open("POST", `${URL_API}/analisis`)
    peticion.responseType = "text"
    peticion.upload.onprogress = (evento) => {
      if (evento.lengthComputable) alProgreso(evento.loaded / evento.total)
    }
    peticion.onload = () => {
      let cuerpo: unknown = null
      try {
        cuerpo = JSON.parse(peticion.responseText)
      } catch {
        // Respuesta sin JSON: se usa el mensaje genérico
      }
      if (peticion.status === 202 && cuerpo) {
        resolver(cuerpo as AnalisisCreado)
        return
      }
      const texto =
        cuerpo && typeof cuerpo === "object" && "detail" in cuerpo && typeof cuerpo.detail === "string"
          ? cuerpo.detail
          : (POR_CODIGO[peticion.status] ?? `El servidor respondió con un error ${peticion.status}.`)
      rechazar(new ErrorApi(peticion.status, texto))
    }
    peticion.onerror = () => rechazar(new ErrorApi(0, SIN_CONEXION))
    peticion.onabort = () => rechazar(new DOMException("Subida cancelada", "AbortError"))
    peticion.send(formulario({ video: archivo }, archivo.name))
  })
  return { promesa, cancelar: () => peticion.abort() }
}
