import { useEffect, useRef, type ComponentPropsWithoutRef } from "react"
import { useInView, useMotionValue, useSpring } from "motion/react"

import { cn } from "@/lib/utils"
import { useMovimientoReducido } from "@/hooks/sistema"

interface NumberTickerProps extends ComponentPropsWithoutRef<"span"> {
  value: number
  startValue?: number
  direction?: "up" | "down"
  delay?: number
  decimalPlaces?: number
}

// Cifras en español: coma decimal y sin ceros sobrantes, como el resto del informe
function formatear(valor: number, decimales: number): string {
  return Intl.NumberFormat("es-ES", {
    minimumFractionDigits: Number.isInteger(valor) ? 0 : decimales,
    maximumFractionDigits: decimales,
  }).format(Number(valor.toFixed(decimales)))
}

export function NumberTicker({
  value,
  startValue = 0,
  direction = "up",
  delay = 0,
  className,
  decimalPlaces = 0,
  ...props
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const quieto = useMovimientoReducido()
  const motionValue = useMotionValue(direction === "down" ? value : startValue)
  // Más rápido que el muelle por defecto, que tardaba unos 5 s en llegar a la cifra
  const springValue = useSpring(motionValue, {
    damping: 40,
    stiffness: 150,
  })
  const isInView = useInView(ref, { once: true, margin: "0px" })

  useEffect(() => {
    if (quieto) return
    let timer: ReturnType<typeof setTimeout> | null = null

    if (isInView) {
      timer = setTimeout(() => {
        motionValue.set(direction === "down" ? startValue : value)
      }, delay * 1000)
    }

    return () => {
      if (timer !== null) {
        clearTimeout(timer)
      }
    }
  }, [motionValue, isInView, delay, value, direction, startValue, quieto])

  useEffect(() => {
    const escribir = (cifra: number) => {
      if (ref.current) ref.current.textContent = formatear(cifra, decimalPlaces)
    }
    const alCambiar = springValue.on("change", escribir)
    // El muelle se detiene cerca del objetivo: al acabar se escribe el valor exacto
    const alTerminar = springValue.on("animationComplete", () => escribir(direction === "down" ? startValue : value))
    return () => {
      alCambiar()
      alTerminar()
    }
  }, [springValue, decimalPlaces, value, direction, startValue])

  // Con reducir movimiento la cifra aparece ya con su valor, sin contar
  const inicial = quieto ? value : direction === "down" ? value : startValue

  return (
    <span ref={ref} className={cn("inline-block tabular-nums", className)} {...props}>
      {formatear(inicial, decimalPlaces)}
    </span>
  )
}
