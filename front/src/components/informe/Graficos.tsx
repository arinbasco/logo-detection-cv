import type { MarcaInforme } from "@/api/cliente"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { confianza, nombreMarca, numero } from "@/lib/formato"

/** Una pista por marca con los tramos del vídeo en que aparece. */
export function LineaTiempo({
  marcas,
  tramos,
  duracion,
}: {
  marcas: MarcaInforme[]
  tramos: Map<string, Array<[number, number]>>
  duracion: number
}) {
  const porcentaje = (segundos: number) => `${(Math.min(segundos, duracion) / duracion) * 100}%`
  return (
    <div className="flex flex-col gap-4">
      {marcas.map(({ marca }) => {
        const lista = tramos.get(marca) ?? []
        const nombre = nombreMarca(marca)
        return (
          <div key={marca} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-4 font-datos text-xs">
              <span>{nombre} en el tiempo</span>
              <span>0 s · {numero(duracion)} s</span>
            </div>
            <div className="relative h-5 bg-pista" aria-hidden="true">
              {lista.map(([inicio, fin]) => (
                <div
                  key={inicio}
                  className="absolute top-0 h-5 bg-negro"
                  style={{ left: porcentaje(inicio), width: `calc(${porcentaje(fin)} - ${porcentaje(inicio)})` }}
                />
              ))}
            </div>
            <p className="sr-only">
              {nombre} aparece en {lista.length} {lista.length === 1 ? "tramo" : "tramos"}:{" "}
              {lista.map(([inicio, fin]) => `del segundo ${numero(inicio)} al ${numero(Math.min(fin, duracion))}`).join(", ")}.
            </p>
          </div>
        )
      })}
    </div>
  )
}

/** Tabla de tiempo por marca, ordenada de más a menos segundos como la devuelve el backend. */
export function TablaMarcas({ marcas }: { marcas: MarcaInforme[] }) {
  return (
    <Table className="text-[15px]">
      <TableHeader>
        <TableRow className="border-b-[3px] border-negro hover:bg-transparent">
          <TableHead className="h-auto py-2.5 pr-2 pl-0 font-semibold text-negro">Marca</TableHead>
          <TableHead className="h-auto px-2 py-2.5 text-right font-semibold text-negro">Segundos</TableHead>
          <TableHead className="h-auto px-2 py-2.5 text-right font-semibold text-negro">% vídeo</TableHead>
          <TableHead className="h-auto py-2.5 pr-0 pl-2 text-right font-semibold text-negro">Confianza</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {marcas.map((m) => (
          <TableRow key={m.marca} className="border-b border-negro hover:bg-transparent">
            <TableCell className="py-3 pr-2 pl-0 font-semibold">{nombreMarca(m.marca)}</TableCell>
            <TableCell className="px-2 py-3 text-right font-datos">{numero(m.segundos)}</TableCell>
            <TableCell className="px-2 py-3 text-right font-datos">{numero(m.porcentaje)}</TableCell>
            <TableCell className="py-3 pr-0 pl-2 text-right font-datos">{confianza(m.confianza_media)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** Barras horizontales del porcentaje del vídeo de cada marca, de más a menos. */
export function BarrasMarcas({ marcas }: { marcas: MarcaInforme[] }) {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      {marcas.map((m) => (
        <div key={m.marca} className="flex flex-col gap-1.5">
          <div className="flex justify-between gap-4 font-semibold">
            <span>{nombreMarca(m.marca)}</span>
            <span className="font-datos">{numero(m.porcentaje)} %</span>
          </div>
          <div className="h-3.5 bg-pista">
            <div className="box-border h-3.5 border-2 border-negro bg-amarillo" style={{ width: `${Math.min(100, m.porcentaje)}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}
