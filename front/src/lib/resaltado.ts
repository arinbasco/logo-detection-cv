/** Resaltado de las cifras del resumen que coinciden con un valor de los hallazgos. */

import type { Hallazgo } from "@/api/cliente"

/** Comienzo de la nota final de limitaciones, que el backend añade siempre al resumen. */
const INICIO_NOTA = "El modelo reconoce"

/** Separa el resumen de la nota final, que se muestra aparte, en gris y más pequeña. */
export function separarNota(resumen: string): { texto: string; nota: string } {
  const posicion = resumen.indexOf(INICIO_NOTA)
  if (posicion <= 0) return { texto: resumen, nota: "" }
  return { texto: resumen.slice(0, posicion).trim(), nota: resumen.slice(posicion).trim() }
}

/**
 * Todos los números que aparecen en los datos de los hallazgos, de cualquier tipo.
 * Se recorren sin conocer el tipo, así que un hallazgo nuevo no rompe nada.
 */
export function valoresDeHallazgos(hallazgos: Hallazgo[]): Set<number> {
  const valores = new Set<number>()
  const recorrer = (dato: unknown): void => {
    if (typeof dato === "number" && Number.isFinite(dato)) valores.add(dato)
    else if (Array.isArray(dato)) dato.forEach(recorrer)
    else if (dato && typeof dato === "object") Object.values(dato).forEach(recorrer)
  }
  hallazgos.forEach((h) => recorrer(h.datos))
  return valores
}

export interface Trozo {
  texto: string
  resaltado: boolean
}

// Una cifra con coma decimal y, si la lleva, su unidad: «21,1 segundos», «100 %», «4 fotogramas»
const CIFRA = /(\d+(?:,\d+)?)(\s(?:%|segundos?|fotogramas?|veces))?/g

/** Trocea el texto marcando las cifras que justifica algún hallazgo. */
export function trocear(texto: string, permitidos: Set<number>): Trozo[] {
  const trozos: Trozo[] = []
  let ultimo = 0
  for (const coincidencia of texto.matchAll(CIFRA)) {
    const valor = Number(coincidencia[1].replace(",", "."))
    if (!permitidos.has(valor)) continue
    const inicio = coincidencia.index
    if (inicio > ultimo) trozos.push({ texto: texto.slice(ultimo, inicio), resaltado: false })
    // Espacio duro para que la cifra y su unidad no se separen al final de una línea
    trozos.push({ texto: coincidencia[0].replace(" ", " "), resaltado: true })
    ultimo = inicio + coincidencia[0].length
  }
  if (ultimo < texto.length) trozos.push({ texto: texto.slice(ultimo), resaltado: false })
  return trozos
}
