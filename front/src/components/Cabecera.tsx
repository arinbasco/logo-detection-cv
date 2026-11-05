import { useState } from "react"
import { Link, useLocation } from "react-router"
import { ListIcon, XIcon } from "@phosphor-icons/react"

import { cn } from "@/lib/utils"

export type Seccion = "analisis" | "en-vivo"

const ENLACES: Array<{ seccion: Seccion; ruta: string; texto: string }> = [
  { seccion: "analisis", ruta: "/analisis", texto: "Análisis" },
  { seccion: "en-vivo", ruta: "/en-vivo", texto: "En vivo" },
]

/** Barra de navegación. En móvil los enlaces se recogen tras el botón Menú. */
export function Cabecera({ seccion }: { seccion: Seccion | null }) {
  const [abierta, setAbierta] = useState(false)
  const { pathname } = useLocation()

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b-[3px] border-negro margen-composicion bg-amarillo py-5">
      <Link to="/analisis" viewTransition className="font-titular text-[22px] font-black text-negro no-underline">
        Detección de logos
      </Link>
      <button
        type="button"
        className="inline-flex min-h-12 items-center gap-2 border-2 border-negro px-4 font-semibold sm:hidden"
        aria-expanded={abierta}
        aria-controls="navegacion-principal"
        onClick={() => setAbierta((valor) => !valor)}
      >
        {abierta ? <XIcon className="size-5" aria-hidden="true" /> : <ListIcon className="size-5" aria-hidden="true" />}
        Menú
      </button>
      <nav
        id="navegacion-principal"
        aria-label="Principal"
        className={cn("w-full flex-col gap-2 sm:flex sm:w-auto sm:flex-row", abierta ? "flex" : "hidden")}
      >
        {ENLACES.map((enlace) => {
          const activa = seccion === enlace.seccion
          return (
            <Link
              key={enlace.ruta}
              to={enlace.ruta}
              viewTransition
              aria-current={pathname === enlace.ruta ? "page" : undefined}
              onClick={() => setAbierta(false)}
              className={cn(
                "border-2 border-negro px-5 py-3 font-semibold no-underline",
                activa ? "bg-negro text-amarillo" : "text-negro hover:bg-negro/10",
              )}
            >
              {enlace.texto}
            </Link>
          )
        })}
      </nav>
    </header>
  )
}
