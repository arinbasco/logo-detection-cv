/** Preferencias y estado del sistema: reducir movimiento y conexión a la red. */

import { useSyncExternalStore } from "react"
import { flushSync } from "react-dom"

const CONSULTA_MOVIMIENTO = "(prefers-reduced-motion: reduce)"

export function prefiereMenosMovimiento(): boolean {
  return window.matchMedia(CONSULTA_MOVIMIENTO).matches
}

function suscribirMovimiento(avisar: () => void): () => void {
  const consulta = window.matchMedia(CONSULTA_MOVIMIENTO)
  consulta.addEventListener("change", avisar)
  return () => consulta.removeEventListener("change", avisar)
}

/** true si el sistema tiene activado reducir el movimiento. */
export function useMovimientoReducido(): boolean {
  return useSyncExternalStore(suscribirMovimiento, prefiereMenosMovimiento)
}

function suscribirConexion(avisar: () => void): () => void {
  window.addEventListener("online", avisar)
  window.addEventListener("offline", avisar)
  return () => {
    window.removeEventListener("online", avisar)
    window.removeEventListener("offline", avisar)
  }
}

/** true mientras el navegador tiene conexión. */
export function useEnLinea(): boolean {
  return useSyncExternalStore(suscribirConexion, () => navigator.onLine)
}

/**
 * Ejecuta un cambio de pantalla con View Transitions si el navegador la tiene y no se pide
 * menos movimiento. El cambio de React se aplica de golpe para que la captura sea la nueva.
 */
export function conTransicion(cambio: () => void): void {
  if (!document.startViewTransition || prefiereMenosMovimiento()) {
    cambio()
    return
  }
  document.startViewTransition(() => flushSync(cambio))
}
