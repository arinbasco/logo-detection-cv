import { memo } from "react"

import { aPantalla, type Rect, type Tamano } from "@/lib/cajas"
import { confianza, nombreMarca } from "@/lib/formato"
import { trazoAMano } from "@/lib/trazo"

export interface CajaVisible {
  clave: string
  marca: string
  confianza: number
  caja: number[]
}

interface Props {
  cajas: CajaVisible[]
  origen: Tamano // tamaño de la imagen en la que vienen las cajas
  area: Rect // zona del vídeo en pantalla, sin las franjas negras
  contenedor: Tamano
}

const ALTO_ETIQUETA = 30

/**
 * Capa SVG con las cajas encima del <video>, nunca sobre la imagen. Doble trazo de
 * rotulador, blanco y ancho debajo y amarillo encima, con la etiqueta en la esquina.
 */
export const CapaCajas = memo(function CapaCajas({ cajas, origen, area, contenedor }: Props) {
  if (!origen.ancho || !origen.alto || !contenedor.ancho || !cajas.length) return null
  const visibles = cajas.map((c) => ({ ...c, r: aPantalla(c.caja, origen, area) }))

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <svg
        className="absolute inset-0 overflow-visible"
        width={contenedor.ancho}
        height={contenedor.alto}
        viewBox={`0 0 ${contenedor.ancho} ${contenedor.alto}`}
      >
        {visibles.map(({ clave, r }) => {
          const d = trazoAMano(r.x, r.y, r.ancho, r.alto, clave)
          const grosor = Math.max(5, Math.min(10, Math.min(r.ancho, r.alto) * 0.08))
          return (
            <g key={clave}>
              <path d={d} fill="none" stroke="#FFFFFF" strokeWidth={grosor} strokeLinecap="round" strokeLinejoin="round" />
              <path d={d} fill="none" stroke="#F5D02E" strokeWidth={grosor * 0.45} strokeLinecap="round" strokeLinejoin="round" />
            </g>
          )
        })}
      </svg>
      {visibles.map(({ clave, marca, confianza: valor, r }) => (
        <span
          key={clave}
          className="absolute bg-amarillo px-2.5 py-1.5 font-datos text-aviso leading-none font-semibold whitespace-nowrap text-negro"
          style={{
            left: `max(0px, min(${r.x - 4}px, ${contenedor.ancho}px - var(--u) * 140))`,
            // Encima de la esquina superior izquierda, o dentro si no cabe. La etiqueta crece con --u
            top:
              r.y >= ALTO_ETIQUETA + 4
                ? `max(0px, ${r.y}px - var(--u) * ${ALTO_ETIQUETA + 4})`
                : `calc(${r.y}px + var(--u) * 8)`,
          }}
        >
          {nombreMarca(marca)} {confianza(valor)}
        </span>
      ))}
    </div>
  )
})
