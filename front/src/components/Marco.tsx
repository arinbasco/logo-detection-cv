import { useEffect, useRef, useState } from "react"
import { Outlet, ScrollRestoration, useLocation, useOutletContext } from "react-router"

import { Cabecera, type Seccion } from "@/components/Cabecera"
import { useEnLinea } from "@/hooks/sistema"
import { cn } from "@/lib/utils"

interface ContextoMarco {
  setSeccionInforme: (seccion: Seccion) => void
}

/** El informe marca en la navegación la sección de la que viene: Análisis o En vivo. */
export function useSeccionInforme(): ContextoMarco["setSeccionInforme"] {
  return useOutletContext<ContextoMarco>().setSeccionInforme
}

function AvisoSinConexion() {
  const enLinea = useEnLinea()
  if (enLinea) return null
  return (
    <p role="status" className="margen-composicion m-0 bg-negro py-3 font-datos text-sm text-amarillo">
      Sin conexión. Todo seguirá solo en cuanto vuelva la red.
    </p>
  )
}

/** Estructura común de las páginas: navegación, aviso de conexión y contenido. */
export function Marco() {
  const { pathname } = useLocation()
  const esInforme = pathname.startsWith("/informe/")
  const [seccionInforme, setSeccionInforme] = useState<Seccion>("analisis")
  const principal = useRef<HTMLElement>(null)
  const rutaAnterior = useRef(pathname)

  const seccion: Seccion | null = esInforme
    ? seccionInforme
    : pathname.startsWith("/en-vivo")
      ? "en-vivo"
      : pathname.startsWith("/analisis")
        ? "analisis"
        : null

  // Al cambiar de página, el foco pasa al contenido para que el lector de pantalla lo anuncie
  // Se compara con la dirección anterior, no con un «primera vez»: así un efecto que se
  // ejecuta dos veces al montar, como en StrictMode, no roba el foco al abrir la web
  useEffect(() => {
    if (rutaAnterior.current === pathname) return
    rutaAnterior.current = pathname
    principal.current?.focus({ preventScroll: true })
  }, [pathname])

  return (
    <div className={cn("min-h-screen", esInforme ? "bg-blanco" : "bg-amarillo")}>
      <a
        href="#contenido"
        className="sr-only bg-negro px-4 py-3 font-semibold text-amarillo focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50"
      >
        Saltar al contenido
      </a>
      <Cabecera seccion={seccion} />
      <AvisoSinConexion />
      <main id="contenido" ref={principal} tabIndex={-1} className="outline-none">
        <Outlet context={{ setSeccionInforme } satisfies ContextoMarco} />
      </main>
      <ScrollRestoration />
    </div>
  )
}
