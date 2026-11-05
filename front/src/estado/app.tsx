/**
 * Estado compartido entre páginas: la configuración del backend, las marcas y los
 * archivos de vídeo elegidos, que siguen en memoria para verlos en el informe.
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"

import type { Configuracion } from "@/api/cliente"

export interface AnalisisEnCurso {
  id: string
  nombre: string
}

interface ValorApp {
  config: Configuracion
  marcas: string[]
  enVivoDisponible: boolean
  archivoDe: (id: string) => File | undefined
  guardarArchivo: (id: string, archivo: File) => void
  enCurso: AnalisisEnCurso | null
  setEnCurso: (analisis: AnalisisEnCurso | null) => void
}

const ContextoApp = createContext<ValorApp | null>(null)

export function ProveedorApp({ config, marcas, children }: { config: Configuracion; marcas: string[]; children: ReactNode }) {
  const [archivos, setArchivos] = useState<Record<string, File>>({})
  const [enCurso, setEnCurso] = useState<AnalisisEnCurso | null>(null)
  const archivoDe = useCallback((id: string) => archivos[id], [archivos])
  const guardarArchivo = useCallback((id: string, archivo: File) => {
    setArchivos((anteriores) => ({ ...anteriores, [id]: archivo }))
  }, [])
  const valor = useMemo(
    () => ({
      config,
      marcas,
      enVivoDisponible: config.modos.includes("en_vivo"),
      archivoDe,
      guardarArchivo,
      enCurso,
      setEnCurso,
    }),
    [config, marcas, archivoDe, guardarArchivo, enCurso],
  )
  return <ContextoApp.Provider value={valor}>{children}</ContextoApp.Provider>
}

export function useApp(): ValorApp {
  const valor = useContext(ContextoApp)
  if (!valor) throw new Error("useApp necesita ProveedorApp")
  return valor
}
