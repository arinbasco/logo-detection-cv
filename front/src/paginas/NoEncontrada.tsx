import { useEffect } from "react"
import { Link } from "react-router"

import { buttonVariants } from "@/components/ui/button"

export function NoEncontrada() {
  useEffect(() => {
    document.title = "Página no encontrada · Detección de logos"
  }, [])

  return (
    <div className="mx-auto flex max-w-[1280px] flex-col items-start gap-6 px-[clamp(24px,5vw,80px)] pt-14 pb-20">
      <p className="etiqueta-datos m-0">Error 404</p>
      <h1 className="m-0 font-titular text-[clamp(48px,6vw,88px)] leading-none font-black">Esta página no existe.</h1>
      <Link to="/analisis" viewTransition className={buttonVariants({ size: "lg" })}>
        Ir a Análisis
      </Link>
    </div>
  )
}
