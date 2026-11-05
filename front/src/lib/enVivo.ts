/** Captura de fotogramas y cuentas del panel «Hasta ahora» del modo en vivo. */

import { tamanoEnVivo } from "@/lib/cajas"

/** Lo mismo que cuenta el backend: cada fotograma hasta el siguiente, 5 s como máximo. */
const MAXIMO_POR_FOTOGRAMA_S = 5

export interface FotogramaAnalizado {
  t_s: number
  marcas: string[]
}

/** Dibuja el fotograma actual en un canvas de 640 px de lado largo y lo exporta como JPEG de calidad 0,8. */
export function capturar(video: HTMLVideoElement, lienzo: HTMLCanvasElement): Promise<Blob> {
  const { ancho, alto } = tamanoEnVivo({ ancho: video.videoWidth, alto: video.videoHeight })
  lienzo.width = ancho
  lienzo.height = alto
  const contexto = lienzo.getContext("2d")
  if (!contexto) return Promise.reject(new Error("El navegador no puede capturar fotogramas."))
  contexto.drawImage(video, 0, 0, ancho, alto)
  return new Promise((resolver, rechazar) => {
    lienzo.toBlob(
      (imagen) => (imagen ? resolver(imagen) : rechazar(new Error("No se pudo capturar el fotograma."))),
      "image/jpeg",
      0.8,
    )
  })
}

/**
 * Segundos por marca de lo analizado hasta ahora. El último fotograma todavía no cuenta,
 * porque no se sabe hasta cuándo dura: el informe final lo calcula el backend.
 */
export function segundosHastaAhora(fotogramas: FotogramaAnalizado[]): Array<{ marca: string; segundos: number }> {
  const porSegundo = new Map<number, Set<string>>()
  for (const f of fotogramas) {
    const marcas = porSegundo.get(f.t_s) ?? new Set<string>()
    f.marcas.forEach((m) => marcas.add(m))
    porSegundo.set(f.t_s, marcas)
  }
  const segundos = [...porSegundo.keys()].sort((a, b) => a - b)
  const totales = new Map<string, number>()
  segundos.forEach((t, i) => {
    const siguiente = segundos[i + 1]
    if (siguiente === undefined) return
    const peso = Math.min(siguiente - t, MAXIMO_POR_FOTOGRAMA_S)
    for (const marca of porSegundo.get(t) ?? []) totales.set(marca, (totales.get(marca) ?? 0) + peso)
  })
  return [...totales.entries()]
    .map(([marca, total]) => ({ marca, segundos: total }))
    .sort((a, b) => b.segundos - a.segundos || a.marca.localeCompare(b.marca))
}
