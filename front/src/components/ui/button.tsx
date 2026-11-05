import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 cursor-pointer items-center justify-center gap-2.5 rounded-none border-2 border-transparent bg-clip-padding text-base font-semibold whitespace-nowrap no-underline transition-colors select-none active:not-aria-[haspopup]:translate-y-px disabled:cursor-not-allowed disabled:opacity-60 aria-disabled:cursor-not-allowed aria-disabled:opacity-60 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default: "bg-negro text-amarillo hover:bg-black",
        outline: "border-negro bg-transparent text-negro hover:bg-negro hover:text-amarillo",
        invertido: "bg-amarillo text-negro hover:bg-[#ffdf4d]",
        ghost: "text-negro hover:bg-negro/10",
        link: "text-negro underline underline-offset-4 hover:no-underline",
      },
      size: {
        default: "min-h-12 px-6 py-3",
        sm: "min-h-10 px-4 py-2 text-sm",
        lg: "min-h-14 px-7 py-4",
        icon: "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Spinner() {
  return (
    <svg viewBox="0 0 24 24" className="anim-girar size-5" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="square" />
    </svg>
  )
}

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  cargando = false,
  disabled,
  children,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    /** Muestra un indicador de carga dentro del botón y lo desactiva */
    cargando?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || cargando}
      aria-busy={cargando || undefined}
      {...props}
    >
      {asChild ? children : <>{cargando && <Spinner />}{children}</>}
    </Comp>
  )
}

export { Button, buttonVariants }
