import type { MarcaInforme } from "@/api/cliente"
import { NumberTicker } from "@/components/ui/number-ticker"
import { numero } from "@/lib/formato"

function Cifra({ valor, decimales = 0, unidad, etiqueta }: { valor: number; decimales?: number; unidad?: string; etiqueta: string }) {
  const final = `${numero(valor, decimales)}${unidad ? ` ${unidad}` : ""}`
  return (
    <div className="flex flex-col gap-1.5 bg-blanco p-6">
      <span className="font-titular text-[clamp(32px,4vw,44px)] leading-none font-black whitespace-nowrap">
        {/* La cifra que cuenta es solo visual: el lector de pantalla lee la final */}
        <span aria-hidden="true">
          <NumberTicker value={valor} decimalPlaces={decimales} />
          {unidad && ` ${unidad}`}
        </span>
        <span className="sr-only">{final}</span>
      </span>
      <span className="font-datos text-xs uppercase">{etiqueta}</span>
    </div>
  )
}

/** Las cuatro cifras grandes de la marca principal, que cuentan hacia arriba al aparecer. */
export function Cifras({ marca }: { marca: MarcaInforme }) {
  return (
    <section
      aria-label={`Cifras principales de ${marca.marca}`}
      className="grid grid-cols-2 gap-[3px] border-[3px] border-negro bg-negro lg:grid-cols-4"
    >
      <Cifra valor={Math.round(marca.segundos * 10) / 10} decimales={1} unidad="s" etiqueta="en pantalla" />
      <Cifra valor={Math.round(marca.porcentaje * 10) / 10} decimales={1} unidad="%" etiqueta="del vídeo" />
      <Cifra valor={marca.detecciones} etiqueta="detecciones" />
      <Cifra valor={Math.round(marca.confianza_media * 100)} unidad="%" etiqueta="confianza media" />
    </section>
  )
}
