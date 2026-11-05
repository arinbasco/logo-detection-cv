/** Formatos en español: coma decimal, sin ceros sobrantes, y nombres de marca para mostrar. */

/** Número con coma decimal y sin ceros sobrantes, como lo escribe el backend: 12 o 12,5. */
export function numero(valor: number, decimales = 1): string {
  const factor = 10 ** decimales
  const redondeado = Math.round(valor * factor) / factor
  if (Number.isInteger(redondeado)) return String(redondeado)
  return redondeado.toFixed(decimales).replace(".", ",")
}

/** Confianza de 0 a 1 escrita como porcentaje entero: 0,823 es «82 %». */
export function confianza(valor: number): string {
  return `${Math.round(valor * 100)} %`
}

/** Segundo del vídeo como reloj: «00:12», o «00:12,0» con décimas. */
export function reloj(segundos: number, conDecimas = false): string {
  const total = conDecimas ? Math.round(segundos * 10) / 10 : Math.floor(segundos)
  const minutos = Math.floor(total / 60)
  const resto = total - minutos * 60
  const parteEntera = String(Math.floor(resto)).padStart(2, "0")
  const texto = `${String(minutos).padStart(2, "0")}:${parteEntera}`
  return conDecimas ? `${texto},${Math.round((resto % 1) * 10)}` : texto
}

/** Tiempo de espera redondeado para leerlo de un vistazo: «unos 28 segundos», «un minuto». */
export function aproximado(segundos: number): string {
  const s = Math.max(1, Math.round(segundos))
  if (s === 1) return "un segundo"
  if (s < 60) return `unos ${s} segundos`
  const m = Math.round(s / 60)
  return m === 1 ? "un minuto" : `unos ${m} minutos`
}

/** Lo que falta, con el verbo concordado: «queda un minuto», «quedan unos 28 segundos». */
export function quedan(segundos: number): string {
  const texto = aproximado(segundos)
  return `${texto.startsWith("un ") ? "queda" : "quedan"} ${texto}`
}

/** Tamaño de archivo en MB con una cifra decimal. */
export function megas(bytes: number): string {
  return `${numero(bytes / (1024 * 1024))} MB`
}

/**
 * Nombre de la marca para etiquetas, tablas, gráficos y galería. El modelo llama
 * «Apple Inc-» a Apple. El texto del resumen del backend no pasa por aquí.
 */
const NOMBRES_VISIBLES: Record<string, string> = { "Apple Inc-": "Apple" }

export function nombreMarca(marca: string): string {
  return NOMBRES_VISIBLES[marca] ?? marca
}
