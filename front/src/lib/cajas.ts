/** Escalado de las cajas al vídeo en pantalla y agrupación de las detecciones por segundo. */

import type { DeteccionGuardada } from "@/api/cliente"

/** En el modo en vivo el front envía cada fotograma con 640 px de lado largo como máximo. */
export const LADO_EN_VIVO = 640

/** Cuánto se mantiene una caja de una sesión en vivo si no llega otra detección antes. */
export const MANTENER_EN_VIVO_S = 1

export interface Tamano {
  ancho: number
  alto: number
}

export interface Rect {
  x: number
  y: number
  ancho: number
  alto: number
}

/** Tamaño del fotograma que se envía en vivo: reducido a 640 px de lado largo, nunca ampliado. */
export function tamanoEnVivo(video: Tamano): Tamano {
  const escala = Math.min(1, LADO_EN_VIVO / Math.max(video.ancho, video.alto))
  return { ancho: Math.round(video.ancho * escala), alto: Math.round(video.alto * escala) }
}

/** Zona que ocupa la imagen dentro del elemento <video>, quitando las franjas negras. */
export function areaVisible(contenedor: Tamano, video: Tamano): Rect {
  if (!video.ancho || !video.alto) return { x: 0, y: 0, ...contenedor }
  const escala = Math.min(contenedor.ancho / video.ancho, contenedor.alto / video.alto)
  const ancho = video.ancho * escala
  const alto = video.alto * escala
  return { x: (contenedor.ancho - ancho) / 2, y: (contenedor.alto - alto) / 2, ancho, alto }
}

/** Pasa una caja [x1, y1, x2, y2] en píxeles de la imagen de origen a píxeles de pantalla. */
export function aPantalla(caja: number[], origen: Tamano, area: Rect): Rect {
  const [x1, y1, x2, y2] = caja
  const fx = area.ancho / origen.ancho
  const fy = area.alto / origen.alto
  return { x: area.x + x1 * fx, y: area.y + y1 * fy, ancho: (x2 - x1) * fx, alto: (y2 - y1) * fy }
}

export interface Grupo {
  t_s: number
  hasta: number // segundo en que deja de mostrarse
  detecciones: DeteccionGuardada[]
}

/**
 * Agrupa por segundo analizado, una sola vez al cargar. En el modo informe cada grupo se
 * mantiene hasta el siguiente fotograma analizado, intervalo_s después. En una sesión en
 * vivo el backend no da los fotogramas sin detecciones, así que se mantiene hasta la
 * siguiente detección, con 1 segundo como máximo.
 */
export function agrupar(detecciones: DeteccionGuardada[], intervalo_s: number | null): Grupo[] {
  const porSegundo = new Map<number, DeteccionGuardada[]>()
  for (const d of detecciones) {
    const lista = porSegundo.get(d.t_s)
    if (lista) lista.push(d)
    else porSegundo.set(d.t_s, [d])
  }
  const segundos = [...porSegundo.keys()].sort((a, b) => a - b)
  const duracion = intervalo_s ?? MANTENER_EN_VIVO_S
  return segundos.map((t_s, i) => ({
    t_s,
    hasta: Math.min(segundos[i + 1] ?? Infinity, t_s + duracion),
    detecciones: porSegundo.get(t_s) ?? [],
  }))
}

/** Grupo visible en el segundo t: el último analizado que no lo supera, si sigue vigente. */
export function grupoEn(grupos: Grupo[], t: number): number {
  let bajo = 0
  let alto = grupos.length - 1
  let encontrado = -1
  while (bajo <= alto) {
    const medio = (bajo + alto) >> 1
    if (grupos[medio].t_s <= t + 1e-6) {
      encontrado = medio
      bajo = medio + 1
    } else {
      alto = medio - 1
    }
  }
  return encontrado >= 0 && t < grupos[encontrado].hasta ? encontrado : -1
}

/** Tramos en que aparece cada marca, uniendo los que se tocan. */
export function tramosPorMarca(grupos: Grupo[]): Map<string, Array<[number, number]>> {
  const tramos = new Map<string, Array<[number, number]>>()
  for (const grupo of grupos) {
    for (const marca of new Set(grupo.detecciones.map((d) => d.marca))) {
      const lista = tramos.get(marca) ?? []
      const ultimo = lista[lista.length - 1]
      if (ultimo && grupo.t_s <= ultimo[1] + 1e-6) ultimo[1] = Math.max(ultimo[1], grupo.hasta)
      else lista.push([grupo.t_s, grupo.hasta])
      tramos.set(marca, lista)
    }
  }
  return tramos
}
