import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { api, type DeteccionGuardada } from "@/api/cliente"
import { confianza, nombreMarca, reloj } from "@/lib/formato"
import { Limitador } from "@/lib/limitador"

// El backend admite 120 peticiones por minuto en /recortes: se deja margen
const EN_PARALELO = 4
const POR_MINUTO = 100

type Cargar = (recorte: string) => Promise<string>

function Recorte({ deteccion, cargar }: { deteccion: DeteccionGuardada; cargar: Cargar }) {
  const elemento = useRef<HTMLLIElement>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [fallo, setFallo] = useState(false)

  // Solo se pide al acercarse a la pantalla
  useEffect(() => {
    const nodo = elemento.current
    if (!nodo) return
    let vigente = true
    const observador = new IntersectionObserver(
      ([entrada]) => {
        if (!entrada.isIntersecting) return
        observador.disconnect()
        cargar(deteccion.recorte_id).then(
          (direccion) => vigente && setUrl(direccion),
          () => vigente && setFallo(true),
        )
      },
      { rootMargin: "400px 0px" },
    )
    observador.observe(nodo)
    return () => {
      vigente = false
      observador.disconnect()
    }
  }, [deteccion.recorte_id, cargar])

  const marca = nombreMarca(deteccion.marca)
  return (
    <li ref={elemento} className="m-0 flex flex-col gap-1.5">
      <div className="flex aspect-square items-center justify-center overflow-hidden bg-[#2a2a2a] font-datos text-[11px] text-[#bdbdbd]">
        {url ? (
          <img src={url} alt={`Recorte de ${marca} en el segundo ${reloj(deteccion.t_s, true)}`} className="h-full w-full object-contain" />
        ) : (
          <span>{fallo ? "sin imagen" : "recorte"}</span>
        )}
      </div>
      <div className="flex flex-col font-datos text-[11px] leading-snug">
        <span className="font-semibold">{marca}</span>
        <span>
          {reloj(deteccion.t_s)} · {confianza(deteccion.confianza)}
        </span>
      </div>
    </li>
  )
}

/** Galería de recortes, que se cargan al bajar, con 4 peticiones a la vez y 100 por minuto como máximo. */
export function Galeria({ detecciones }: { detecciones: DeteccionGuardada[] }) {
  const limitador = useMemo(() => new Limitador(EN_PARALELO, POR_MINUTO), [])
  // El backend responde con no-store, así que se guardan aquí para no pedirlos dos veces
  const direcciones = useRef(new Map<string, Promise<string>>())

  useEffect(() => {
    const guardadas = direcciones.current
    return () => {
      limitador.vaciar()
      for (const promesa of guardadas.values()) promesa.then(URL.revokeObjectURL, () => {})
      guardadas.clear()
    }
  }, [limitador])

  const cargar = useCallback<Cargar>(
    (recorte) => {
      let promesa = direcciones.current.get(recorte)
      if (!promesa) {
        promesa = limitador.encolar(() => api.recorte(recorte)).then((imagen) => URL.createObjectURL(imagen))
        promesa.catch(() => direcciones.current.delete(recorte))
        direcciones.current.set(recorte, promesa)
      }
      return promesa
    },
    [limitador],
  )

  return (
    <section className="flex flex-col gap-4" aria-labelledby="titulo-recortes">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 id="titulo-recortes" className="m-0 font-titular text-[32px] font-black">
          Recortes
        </h2>
        <span className="font-datos text-xs">
          {detecciones.length} {detecciones.length === 1 ? "imagen" : "imágenes"} · se cargan al bajar
        </span>
      </div>
      <ul role="list" className="m-0 grid list-none grid-cols-3 gap-2.5 p-0 sm:grid-cols-4 lg:grid-cols-8">
        {detecciones.map((d) => (
          <Recorte key={d.id} deteccion={d} cargar={cargar} />
        ))}
      </ul>
    </section>
  )
}
