import { memo, type ComponentProps } from "react"

import { cn } from "@/lib/utils"

type Props = Omit<ComponentProps<"video">, "ref"> & {
  alElemento: (video: HTMLVideoElement | null) => void
}

/**
 * Elemento <video> en blanco y negro. Está memorizado: dibujar las cajas encima no lo
 * vuelve a renderizar, solo cambia la capa SVG.
 */
export const Reproductor = memo(function Reproductor({ alElemento, className, ...props }: Props) {
  return (
    <video
      ref={alElemento}
      playsInline
      preload="metadata"
      className={cn("video-en-gris absolute inset-0 h-full w-full object-contain", className)}
      {...props}
    />
  )
})

/** Grano de fotografía encima del vídeo, sin capturar el ratón. */
export function Grano() {
  return <div className="grano absolute inset-0" aria-hidden="true" />
}
