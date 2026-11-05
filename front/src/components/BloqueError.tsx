import type { ReactNode } from "react"

/** Error en un bloque negro con texto amarillo y la acción para seguir. */
export function BloqueError({ mensaje, children }: { mensaje: string; children?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-col gap-4 bg-negro p-6 text-amarillo">
      <p className="m-0 text-lg leading-snug font-semibold">{mensaje}</p>
      {children && <div className="flex flex-wrap gap-3">{children}</div>}
    </div>
  )
}
