import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"

import { api, ErrorApi, subirVideo, type EstadoAnalisis } from "@/api/cliente"
import { BloqueError } from "@/components/BloqueError"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ZonaSubida } from "@/components/ZonaSubida"
import { useApp } from "@/estado/app"
import { comprobarVideo, numeroDeMuestras } from "@/lib/archivos"
import { aproximado, megas, numero, quedan } from "@/lib/formato"

const CADA_MS = 3000 // consulta del progreso

type Fase =
  | { tipo: "inicio" }
  | { tipo: "comprobando"; archivo: File }
  | { tipo: "elegido"; archivo: File; duracion: number | null }
  | { tipo: "subiendo"; archivo: File; duracion: number | null; fraccion: number }
  | { tipo: "analizando"; id: string; nombre: string; estado: EstadoAnalisis | null; sinConexion: boolean }
  | { tipo: "error"; mensaje: string; archivo?: File; duracion?: number | null; reintentable: boolean }

/** Los errores que se arreglan solos volviendo a intentarlo: otro análisis en curso, la red o la API. */
function esReintentable(error: unknown): boolean {
  return error instanceof ErrorApi && (error.sinConexion || error.estado === 429 || error.estado === 502)
}

function BloqueProgreso({ titulo, porcentaje, detalle }: { titulo: string; porcentaje: number; detalle: string }) {
  const redondeado = Math.round(porcentaje)
  return (
    <div className="flex flex-col gap-3.5 bg-negro p-6 text-amarillo">
      <div className="etiqueta-datos flex flex-wrap justify-between gap-4 tracking-[0.06em]">
        <span className="min-w-0 break-all">{titulo}</span>
        <span>{redondeado} %</span>
      </div>
      <Progress value={redondeado} aria-label={titulo} />
      <p className="m-0 text-base">{detalle}</p>
      {/* Para lectores de pantalla, de diez en diez para no interrumpir a cada consulta */}
      <p className="sr-only" aria-live="polite">
        {`${titulo}, ${Math.floor(redondeado / 10) * 10} %`}
      </p>
    </div>
  )
}

export function Analisis() {
  const { config, guardarArchivo, enCurso, setEnCurso } = useApp()
  const navegar = useNavigate()
  const [fase, setFase] = useState<Fase>(() =>
    enCurso ? { tipo: "analizando", id: enCurso.id, nombre: enCurso.nombre, estado: null, sinConexion: false } : { tipo: "inicio" },
  )
  const zona = useRef<HTMLDivElement>(null)
  const segundosPorFotograma = config.segundos_por_fotograma

  useEffect(() => {
    document.title = "Análisis · Detección de logos"
  }, [])

  const elegir = async (archivo: File) => {
    setFase({ tipo: "comprobando", archivo })
    const comprobacion = await comprobarVideo(archivo)
    if (comprobacion.valido) setFase({ tipo: "elegido", archivo, duracion: comprobacion.duracion })
    else setFase({ tipo: "error", mensaje: comprobacion.mensaje, reintentable: false })
  }

  const subir = (archivo: File, duracion: number | null) => {
    setFase({ tipo: "subiendo", archivo, duracion, fraccion: 0 })
    const subida = subirVideo(archivo, (fraccion) =>
      setFase((actual) => (actual.tipo === "subiendo" ? { ...actual, fraccion } : actual)),
    )
    subida.promesa
      .then((creado) => {
        guardarArchivo(creado.id, archivo)
        setEnCurso({ id: creado.id, nombre: archivo.name })
        setFase({ tipo: "analizando", id: creado.id, nombre: archivo.name, estado: null, sinConexion: false })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        const mensaje = error instanceof Error ? error.message : "No se pudo subir el vídeo."
        setFase({ tipo: "error", mensaje, archivo, duracion, reintentable: esReintentable(error) })
      })
  }

  const elegirOtro = () => {
    setFase({ tipo: "inicio" })
    requestAnimationFrame(() => zona.current?.querySelector("input")?.focus())
  }

  // Consulta el progreso cada 3 s hasta que el análisis termina o se sale de la página
  const idAnalizando = fase.tipo === "analizando" ? fase.id : null
  useEffect(() => {
    if (!idAnalizando) return
    const control = new AbortController()
    let temporizador: ReturnType<typeof setTimeout> | undefined
    const consultar = async () => {
      clearTimeout(temporizador)
      try {
        const estado = await api.estado(idAnalizando, control.signal)
        if (estado.estado === "completado") {
          setEnCurso(null)
          navegar(`/informe/${estado.id}`, { viewTransition: true })
          return
        }
        if (estado.estado === "fallido") {
          setEnCurso(null)
          setFase({ tipo: "error", mensaje: estado.error ?? "El análisis falló.", reintentable: false })
          return
        }
        setFase((actual) => (actual.tipo === "analizando" ? { ...actual, estado, sinConexion: false } : actual))
        temporizador = setTimeout(consultar, CADA_MS)
      } catch (error) {
        if (control.signal.aborted) return
        if (error instanceof ErrorApi && error.sinConexion) {
          // Sin red se sigue intentando, y en cuanto vuelve se consulta sin esperar
          setFase((actual) => (actual.tipo === "analizando" ? { ...actual, sinConexion: true } : actual))
          temporizador = setTimeout(consultar, CADA_MS)
          return
        }
        setEnCurso(null)
        const mensaje = error instanceof Error ? error.message : "No se pudo consultar el análisis."
        setFase({ tipo: "error", mensaje, reintentable: false })
      }
    }
    const alVolverLaRed = () => void consultar()
    window.addEventListener("online", alVolverLaRed)
    void consultar()
    return () => {
      control.abort()
      clearTimeout(temporizador)
      window.removeEventListener("online", alVolverLaRed)
    }
  }, [idAnalizando, navegar, setEnCurso])

  const ocupado = fase.tipo === "subiendo" || fase.tipo === "analizando" || fase.tipo === "comprobando"
  const duracionElegida = fase.tipo === "elegido" ? fase.duracion : null
  const estimacion =
    duracionElegida !== null
      ? `Tiempo estimado · ${aproximado(numeroDeMuestras(duracionElegida, 1) * segundosPorFotograma)} para este vídeo`
      : `Tiempo estimado en este servidor · unos ${numero(segundosPorFotograma)} s por segundo de vídeo`

  return (
    <div className="composicion gap-14">
      <section className="flex flex-[1_1_calc(var(--u)*420)] flex-col gap-6">
        <p className="etiqueta-datos m-0">Modo informe</p>
        <h1 className="m-0 font-titular text-portada leading-none font-black tracking-[-0.02em]">
          Sube un vídeo.
          <br />
          Mide sus marcas.
        </h1>
        <p className="m-0 max-w-[calc(var(--u)*460)] text-lg leading-[1.55]">
          El modelo analiza un fotograma por segundo y calcula cuánto tiempo aparece cada una de sus 15 marcas. Al
          terminar verás el vídeo con las detecciones y el informe.
        </p>
      </section>

      <section className="flex min-w-0 flex-[1_1_calc(var(--u)*460)] flex-col gap-5" aria-label="Subir un vídeo">
        <div ref={zona} className="flex flex-auto">
          <ZonaSubida alElegir={elegir} desactivada={ocupado} descripcion="limites-video" className="flex-auto" />
        </div>
        <p id="limites-video" className="m-0 font-datos text-aviso">
          MP4, MOV, WEBM o AVI · hasta 100 MB, 2 minutos y 4K
        </p>
        <p className="m-0 font-datos text-aviso">{estimacion}</p>

        {fase.tipo === "comprobando" && (
          <p className="m-0 font-datos text-aviso" role="status">
            Comprobando {fase.archivo.name}…
          </p>
        )}

        {fase.tipo === "elegido" && (
          <div className="flex flex-col gap-4 border-[calc(var(--u)*3)] border-negro bg-blanco p-5">
            <div className="flex flex-col gap-1">
              <span className="font-semibold break-all">{fase.archivo.name}</span>
              <span className="font-datos text-aviso">
                {fase.duracion !== null ? `${numero(fase.duracion)} s` : "La duración la comprobará el servidor"} ·{" "}
                {megas(fase.archivo.size)}
              </span>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => subir(fase.archivo, fase.duracion)}>Analizar el vídeo</Button>
              <Button variant="outline" onClick={elegirOtro}>
                Elegir otro
              </Button>
            </div>
          </div>
        )}

        {fase.tipo === "subiendo" && (
          <BloqueProgreso
            titulo={`Subiendo ${fase.archivo.name}`}
            porcentaje={fase.fraccion * 100}
            detalle="Enviando el vídeo al servidor. El análisis empieza en cuanto termine la subida."
          />
        )}

        {fase.tipo === "analizando" && <ProgresoAnalisis fase={fase} />}

        {fase.tipo === "error" && (
          <BloqueError mensaje={fase.mensaje}>
            {fase.reintentable && fase.archivo && (
              <Button variant="invertido" onClick={() => subir(fase.archivo!, fase.duracion ?? null)}>
                Reintentar
              </Button>
            )}
            <Button variant="invertido" onClick={elegirOtro}>
              Elegir otro vídeo
            </Button>
          </BloqueError>
        )}
      </section>
    </div>
  )
}

function ProgresoAnalisis({ fase }: { fase: Extract<Fase, { tipo: "analizando" }> }) {
  const { estado } = fase
  let detalle = "Preparando el análisis…"
  if (estado?.estado === "en_cola") detalle = "En cola. Empieza enseguida."
  if (estado?.estado === "procesando") {
    const total = numeroDeMuestras(estado.duracion_s, estado.intervalo_s ?? 1)
    const actual = Math.min(total, Math.round(estado.progreso * total))
    detalle = `Fotograma ${actual} de ${total} · ${quedan(estado.tiempo_restante_s)}`
  }
  if (fase.sinConexion) detalle = "Sin conexión. La consulta del progreso se reanudará sola al volver la red."
  return (
    <BloqueProgreso titulo={`Analizando ${fase.nombre}`} porcentaje={(estado?.progreso ?? 0) * 100} detalle={detalle} />
  )
}
