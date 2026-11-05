import { useId, useState } from "react"

import { TIPOS_ACEPTADOS } from "@/lib/archivos"
import { cn } from "@/lib/utils"

interface Props {
  alElegir: (archivo: File) => void
  desactivada?: boolean
  descripcion?: string // id del texto con los límites
  titulo?: string
  className?: string
}

/** Zona para arrastrar o elegir un vídeo. Es un label con su input, así que funciona con el teclado. */
export function ZonaSubida({ alElegir, desactivada = false, descripcion, titulo = "Arrastra tu vídeo aquí", className }: Props) {
  const id = useId()
  const [encima, setEncima] = useState(false)

  return (
    <label
      htmlFor={id}
      onDragOver={(evento) => {
        evento.preventDefault()
        if (!desactivada) setEncima(true)
      }}
      onDragLeave={() => setEncima(false)}
      onDrop={(evento) => {
        evento.preventDefault()
        setEncima(false)
        const archivo = evento.dataTransfer.files[0]
        if (archivo && !desactivada) alElegir(archivo)
      }}
      className={cn(
        "relative flex min-h-[calc(var(--u)*280)] cursor-pointer flex-col items-center justify-center gap-3.5 border-[calc(var(--u)*4)] border-dashed border-negro bg-blanco p-8 text-center",
        "has-[input:focus-visible]:outline-[3px] has-[input:focus-visible]:outline-offset-4 has-[input:focus-visible]:outline-negro has-[input:focus-visible]:outline-solid",
        encima && "border-solid bg-amarillo",
        desactivada && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <svg className="size-14" viewBox="0 0 24 24" fill="none" stroke="#111" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 16V4" />
        <path d="M6 10l6-6 6 6" />
        <path d="M4 20h16" />
      </svg>
      <span className="font-titular text-rotulo leading-tight font-black">{titulo}</span>
      <span className="text-apoyo">o pulsa para elegirlo en tu ordenador</span>
      <input
        id={id}
        type="file"
        accept={TIPOS_ACEPTADOS}
        className="sr-only"
        disabled={desactivada}
        aria-describedby={descripcion}
        onChange={(evento) => {
          const archivo = evento.target.files?.[0]
          evento.target.value = "" // permite volver a elegir el mismo archivo
          if (archivo) alElegir(archivo)
        }}
      />
    </label>
  )
}
