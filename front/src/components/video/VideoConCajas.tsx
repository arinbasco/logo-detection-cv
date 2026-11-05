import { useMemo, useState } from "react"

import { tamanoEnVivo, type Grupo } from "@/lib/cajas"
import { confianza, nombreMarca, reloj } from "@/lib/formato"
import { CapaCajas, type CajaVisible } from "./CapaCajas"
import { useAreaVideo, useGrupoActivo } from "./medidas"
import { Grano, Reproductor } from "./Reproductor"

interface Props {
  src: string
  grupos: Grupo[]
  /** Las sesiones en vivo guardan las cajas en píxeles del fotograma de 640 px que se envió */
  enVivo: boolean
}

/** Vídeo del informe con las cajas sincronizadas y su alternativa en texto. */
export function VideoConCajas({ src, grupos, enVivo }: Props) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null)
  const medidas = useAreaVideo(video)
  const indice = useGrupoActivo(video, grupos)
  const grupo = indice >= 0 ? grupos[indice] : null

  const origen = useMemo(
    () => (enVivo ? tamanoEnVivo(medidas.video) : medidas.video),
    [enVivo, medidas.video],
  )
  const cajas = useMemo<CajaVisible[]>(
    () => grupo?.detecciones.map((d) => ({ clave: d.id, marca: d.marca, confianza: d.confianza, caja: d.caja })) ?? [],
    [grupo],
  )

  return (
    <figure className="m-0 flex flex-col gap-3">
      <div className="relative aspect-video w-full overflow-hidden bg-negro">
        <Reproductor src={src} alElemento={setVideo} controls aria-label="Vídeo analizado, con las detecciones dibujadas encima" />
        <Grano />
        <CapaCajas cajas={cajas} origen={origen} area={medidas.area} contenedor={medidas.contenedor} />
      </div>
      <figcaption className="font-datos text-[13px] leading-relaxed">
        {grupo ? (
          <>
            <span className="font-semibold">En pantalla, fotograma del segundo {reloj(grupo.t_s, true)}: </span>
            {grupo.detecciones.map((d) => `${nombreMarca(d.marca)} ${confianza(d.confianza)}`).join(" · ")}
          </>
        ) : (
          "Ninguna detección en este momento del vídeo."
        )}
      </figcaption>
    </figure>
  )
}
