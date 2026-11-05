import { useMemo } from "react"

import type { Hallazgo, Informe } from "@/api/cliente"
import { nombreMarca, numero } from "@/lib/formato"
import { separarNota, trocear, valoresDeHallazgos } from "@/lib/resaltado"

function datosDominante(hallazgos: Hallazgo[]): { marca: string; porcentaje: number } | null {
  const datos = hallazgos.find((h) => h.tipo === "marca_dominante")?.datos
  if (!datos || typeof datos.marca !== "string" || typeof datos.porcentaje_video !== "number") return null
  return { marca: datos.marca, porcentaje: datos.porcentaje_video }
}

/** Titular a partir del hallazgo marca_dominante, con la cifra resaltada con rotulador. */
export function Titular({ hallazgos }: { hallazgos: Hallazgo[] }) {
  const dominante = datosDominante(hallazgos)
  const clases = "m-0 max-w-[1000px] font-titular text-[clamp(48px,6.5vw,96px)] leading-[1.02] font-black tracking-[-0.02em]"
  if (!dominante) return <h1 className={clases}>No se detectó ninguna marca.</h1>
  return (
    <h1 className={clases}>
      {nombreMarca(dominante.marca)} ocupa el{" "}
      <span className="resaltado-titular">{numero(dominante.porcentaje)}{" "}%</span>{" "}
      del vídeo.
    </h1>
  )
}

/** Resumen del backend con cada cifra que justifica un hallazgo resaltada, y la nota final aparte. */
export function Resumen({ informe }: { informe: Informe }) {
  const { texto, nota } = useMemo(() => separarNota(informe.resumen), [informe.resumen])
  const trozos = useMemo(() => trocear(texto, valoresDeHallazgos(informe.hallazgos)), [texto, informe.hallazgos])
  return (
    <>
      <p className="m-0 max-w-[760px] text-xl leading-relaxed">
        {trozos.map((trozo, i) =>
          trozo.resaltado ? (
            <strong key={i} className="resaltado-texto">
              {trozo.texto}
            </strong>
          ) : (
            <span key={i}>{trozo.texto}</span>
          ),
        )}
      </p>
      {nota && <p className="m-0 max-w-[760px] text-sm leading-relaxed text-gris">{nota}</p>}
    </>
  )
}
