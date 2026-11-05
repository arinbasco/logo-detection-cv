import { useEffect, useState } from "react"

import { api, ErrorApi, type Configuracion } from "@/api/cliente"
import { Button } from "@/components/ui/button"
import { prefiereMenosMovimiento } from "@/hooks/sistema"
import { nombreMarca } from "@/lib/formato"
import filaDePantallas from "@/assets/fila-de-pantallas.jpg"

/** Las 15 marcas del modelo, para la cinta mientras llega GET /marcas o si la API del modelo duerme. */
const MARCAS_CONOCIDAS = [
  "Adidas", "Apple Inc-", "Chanel", "Coca-Cola", "Emirates", "Hard Rock Cafe", "Mercedes-Benz",
  "NFL", "Nike", "Pepsi", "Puma", "Starbucks", "The North Face", "Toyota", "Under Armour",
]

const DURACION_MINIMA_MS = 3800 // lo que tarda la animación, hasta que la barra se llena
const AVISO_DESPERTAR_MS = 5000
const LIMITE_MS = 90_000
const TIEMPO_POR_PETICION_MS = 15_000
const PAUSA_ENTRE_INTENTOS_MS = 2000

// Trazo de la maqueta alrededor de «logos» y de la pantalla de la ilustración
const TRAZO_TITULO =
  "M10 18 C 120 8, 300 6, 410 14 C 416 70, 414 120, 408 156 C 300 164, 120 160, 12 152 C 6 110, 4 60, 14 10"
const TRAZO_FOTO =
  "M8 14 C 80 4, 180 6, 252 12 C 258 90, 256 180, 250 250 C 170 256, 90 254, 10 248 C 4 170, 2 90, 10 8"

const esperar = (ms: number, senal: AbortSignal) =>
  new Promise<void>((resolver) => {
    const temporizador = setTimeout(resolver, ms)
    senal.addEventListener("abort", () => clearTimeout(temporizador), { once: true })
  })

/** Repite la petición hasta que responde, mientras no se cancele. Así se espera a que el servidor despierte. */
async function hastaQueResponda<T>(pedir: (senal: AbortSignal) => Promise<T>, senal: AbortSignal): Promise<T> {
  for (;;) {
    try {
      return await pedir(AbortSignal.any([senal, AbortSignal.timeout(TIEMPO_POR_PETICION_MS)]))
    } catch (error) {
      if (senal.aborted) throw error
      if (error instanceof ErrorApi && error.estado >= 400 && error.estado < 500 && error.estado !== 429) throw error
    }
    await esperar(PAUSA_ENTRE_INTENTOS_MS, senal)
    if (senal.aborted) throw new DOMException("Cancelado", "AbortError")
  }
}

interface Props {
  alTerminar: (config: Configuracion, marcas: string[]) => void
}

/** Pantalla de carga: aparece una vez al abrir la web y despierta al servidor. */
export function PantallaCarga({ alTerminar }: Props) {
  const [intento, setIntento] = useState(0)
  const [despertando, setDespertando] = useState(false)
  const [fallo, setFallo] = useState(false)
  const [marcas, setMarcas] = useState(MARCAS_CONOCIDAS)

  useEffect(() => {
    const control = new AbortController()
    const inicio = performance.now()
    const aviso = setTimeout(() => setDespertando(true), AVISO_DESPERTAR_MS)
    const limite = setTimeout(() => {
      control.abort()
      setFallo(true)
    }, LIMITE_MS)

    let marcasLeidas = MARCAS_CONOCIDAS
    api
      .marcas(control.signal)
      .then((lista) => {
        if (lista.length) {
          marcasLeidas = lista
          setMarcas(lista)
        }
      })
      .catch(() => {}) // sin la API del modelo la cinta usa la lista conocida

    Promise.all([hastaQueResponda(api.salud, control.signal), hastaQueResponda(api.config, control.signal)])
      .then(async ([, config]) => {
        // Como mínimo dura lo que su animación, salvo que se pida menos movimiento
        const minimo = prefiereMenosMovimiento() ? 0 : DURACION_MINIMA_MS
        await esperar(Math.max(0, minimo - (performance.now() - inicio)), control.signal)
        if (!control.signal.aborted) alTerminar(config, marcasLeidas)
      })
      .catch(() => {
        if (!control.signal.aborted) setFallo(true)
      })

    return () => {
      control.abort()
      clearTimeout(aviso)
      clearTimeout(limite)
    }
  }, [intento, alTerminar])

  const reintentar = () => {
    setFallo(false)
    setDespertando(false)
    setIntento((n) => n + 1)
  }

  const cinta = marcas.map(nombreMarca)

  return (
    <div className="flex min-h-screen flex-col overflow-hidden bg-amarillo text-negro">
      <div className="flex flex-auto flex-wrap">
        <section className="flex min-w-0 flex-[999_1_560px] flex-col justify-between gap-10 px-[clamp(24px,5vw,80px)] py-12">
          <div className="etiqueta-datos flex flex-wrap justify-between gap-6" aria-live="polite">
            <span>{fallo ? "Sin respuesta" : despertando ? "Despertando el servidor, puede tardar un minuto" : "Cargando modelo"}</span>
            <span>YOLO26n · 15 marcas</span>
          </div>

          <div className="flex flex-col gap-8">
            <h1 className="m-0 font-titular text-[clamp(64px,8.6vw,140px)] leading-[0.98] font-black tracking-[-0.02em]">
              Detección
              <br />
              de{" "}
              <span className="relative inline-block px-[0.12em]">
                logos
                <svg
                  viewBox="0 0 420 170"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                  className="absolute top-[-0.02em] left-[-0.08em] h-[1.12em] w-[calc(100%+0.16em)] overflow-visible"
                >
                  <path className="anim-trazo" d={TRAZO_TITULO} fill="none" stroke="#FFFFFF" strokeWidth="20" strokeLinecap="round" strokeLinejoin="round" />
                  <path className="anim-trazo" d={TRAZO_TITULO} fill="none" stroke="#111111" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span
                  aria-hidden="true"
                  className="anim-etiqueta absolute top-[-0.62em] left-[-0.06em] bg-negro px-2.5 py-1.5 font-datos text-[0.13em] font-semibold tracking-[0.04em] whitespace-nowrap text-amarillo"
                >
                  logo 0,98
                </span>
              </span>
            </h1>
            <p className="m-0 max-w-[520px] text-[clamp(18px,1.5vw,22px)] leading-normal font-semibold">
              Un modelo que mira cada fotograma y mide cuánto tiempo aparece cada marca en pantalla.
            </p>
            {fallo && (
              <div role="alert" className="flex max-w-[560px] flex-col gap-4 bg-negro p-6 text-amarillo">
                <p className="m-0 text-lg leading-snug font-semibold">
                  El servidor no responde. Comprueba tu conexión o vuelve a intentarlo en un momento.
                </p>
                <div>
                  <Button variant="invertido" onClick={reintentar}>
                    Reintentar
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1.5 text-base">
            <span className="font-semibold">Computer Vision · P7 IA · Factoría F5</span>
            <span>Ari Basconsuelo</span>
          </div>
        </section>

        <figure className="relative m-0 min-h-[260px] flex-[1_1_420px] overflow-hidden bg-[#8a8a8a] sm:min-h-[420px]">
          {/* La imagen y la caja comparten el mismo sistema de coordenadas, así la caja no se descoloca */}
          <svg viewBox="0 0 1000 1300" preserveAspectRatio="xMaxYMid slice" className="absolute inset-0 h-full w-full" role="img" aria-label="Fila de pantallas en blanco y negro, una de ellas marcada como detección">
            <image href={filaDePantallas} width="1000" height="1300" />
            <g transform="translate(632 400) scale(0.99 1.77)">
              <path className="anim-trazo-2" d={TRAZO_FOTO} fill="none" stroke="#FFFFFF" strokeWidth="18" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
              <path className="anim-trazo-2" d={TRAZO_FOTO} fill="none" stroke="#F5D02E" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </g>
            <g className="anim-etiqueta-2" aria-hidden="true">
              <rect x="626" y="342" width="196" height="44" fill="#F5D02E" />
              <text x="642" y="372" fill="#111111" fontFamily="IBM Plex Mono, monospace" fontWeight="600" fontSize="21">
                detección 0,91
              </text>
            </g>
          </svg>
        </figure>
      </div>

      <div className="bg-negro text-amarillo">
        <div className="h-1 bg-amarillo/20">
          <div className="anim-barra h-1 w-0 bg-amarillo" />
        </div>
        <div className="overflow-hidden py-[18px]">
          <div className="anim-cinta flex w-max gap-10 font-datos text-lg font-semibold tracking-[0.06em] whitespace-nowrap uppercase">
            {[0, 1].map((copia) =>
              cinta.map((marca, i) => (
                <span key={`${copia}-${i}`} className="flex gap-10" aria-hidden={copia === 1 || undefined}>
                  <span>{marca}</span>
                  <span aria-hidden="true">·</span>
                </span>
              )),
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
