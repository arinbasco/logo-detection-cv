/**
 * Trazos de rotulador para las cajas de detección: nunca rectángulos perfectos.
 *
 * Cada caja es un trazado de cuatro curvas con las esquinas un poco irregulares y algo de
 * solape al cerrar, como en la maqueta. La irregularidad sale de una semilla calculada con
 * la clave de la caja, así que la misma caja dibuja siempre la misma forma y no tiembla.
 */

function semilla(clave: string): number {
  let h = 2166136261 // FNV-1a de 32 bits
  for (let i = 0; i < clave.length; i++) {
    h ^= clave.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/** Generador pseudoaleatorio mulberry32: mismos números para la misma semilla. */
function aleatorio(inicial: number): () => number {
  let estado = inicial
  return () => {
    estado = (estado + 0x6d2b79f5) | 0
    let t = Math.imul(estado ^ (estado >>> 15), 1 | estado)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const p = (x: number, y: number) => `${x.toFixed(1)} ${y.toFixed(1)}`

/** Trazado SVG a mano alzada alrededor del rectángulo, en las mismas unidades que recibe. */
export function trazoAMano(x: number, y: number, ancho: number, alto: number, clave: string): string {
  const r = aleatorio(semilla(clave))
  const j = Math.max(1.5, Math.min(7, Math.min(ancho, alto) * 0.05))
  const fuera = () => j * (0.3 + r() * 0.9) // siempre hacia fuera de la caja
  const libre = () => j * (r() * 2 - 1)
  const x2 = x + ancho
  const y2 = y + alto
  return [
    `M ${p(x + libre(), y + fuera())}`,
    `C ${p(x + ancho * 0.3, y - fuera())}, ${p(x + ancho * 0.7, y - fuera())}, ${p(x2 + libre(), y + libre())}`,
    `C ${p(x2 + fuera(), y + alto * 0.35)}, ${p(x2 + fuera(), y + alto * 0.7)}, ${p(x2 - fuera(), y2 + libre())}`,
    `C ${p(x + ancho * 0.7, y2 + fuera())}, ${p(x + ancho * 0.3, y2 + fuera())}, ${p(x + libre(), y2 - fuera())}`,
    // La última curva pasa del punto de partida, como el rotulador al cerrar la caja
    `C ${p(x - fuera(), y + alto * 0.7)}, ${p(x - fuera(), y + alto * 0.3)}, ${p(x + j * 1.6, y - j * 0.9)}`,
  ].join(" ")
}
