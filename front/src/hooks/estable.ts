import { useCallback, useLayoutEffect, useRef } from "react"

/**
 * Función con identidad fija que siempre llama a la última versión de fn. Sirve para pasar
 * manejadores a componentes memorizados, como el reproductor, sin volver a renderizarlos.
 */
export function useEstable<A extends unknown[], R>(fn: (...argumentos: A) => R): (...argumentos: A) => R {
  const actual = useRef(fn)
  useLayoutEffect(() => {
    actual.current = fn
  })
  return useCallback((...argumentos: A) => actual.current(...argumentos), [])
}
