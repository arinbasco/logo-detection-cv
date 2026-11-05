import { useEffect, useMemo, useState } from "react"
import { Link, useParams } from "react-router"

import { api, ErrorApi, type DeteccionGuardada, type EstadoAnalisis, type Informe as DatosInforme } from "@/api/cliente"
import { BloqueError } from "@/components/BloqueError"
import { Cifras } from "@/components/informe/Cifras"
import { BarrasMarcas, LineaTiempo, TablaMarcas } from "@/components/informe/Graficos"
import { Galeria } from "@/components/informe/Galeria"
import { Resumen, Titular } from "@/components/informe/Resumen"
import { useSeccionInforme } from "@/components/Marco"
import { Button, buttonVariants } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { VideoConCajas } from "@/components/video/VideoConCajas"
import { ZonaSubida } from "@/components/ZonaSubida"
import { useApp } from "@/estado/app"
import { leerDuracion } from "@/lib/archivos"
import { agrupar, tramosPorMarca } from "@/lib/cajas"
import { numero } from "@/lib/formato"

const CADA_MS = 3000

type Fase =
  | { tipo: "cargando" }
  | { tipo: "esperando"; estado: EstadoAnalisis }
  | { tipo: "error"; mensaje: string; reintentable: boolean }
  | { tipo: "listo"; estado: EstadoAnalisis; informe: DatosInforme; detecciones: DeteccionGuardada[] }

export function Informe() {
  const { id = "" } = useParams()
  const setSeccion = useSeccionInforme()
  const [fase, setFase] = useState<Fase>({ tipo: "cargando" })
  const [intento, setIntento] = useState(0)

  // Si el análisis todavía no ha terminado, se espera consultando su estado cada 3 s
  useEffect(() => {
    const control = new AbortController()
    let temporizador: ReturnType<typeof setTimeout> | undefined
    const cargar = async () => {
      try {
        const estado = await api.estado(id, control.signal)
        setSeccion(estado.modo === "en_vivo" ? "en-vivo" : "analisis")
        if (estado.estado === "completado") {
          const [informe, detecciones] = await Promise.all([
            api.informe(id, control.signal),
            api.detecciones(id, control.signal),
          ])
          setFase({ tipo: "listo", estado, informe, detecciones })
        } else if (estado.estado === "fallido") {
          setFase({ tipo: "error", mensaje: estado.error ?? "El análisis falló y no tiene resultados.", reintentable: false })
        } else {
          setFase({ tipo: "esperando", estado })
          temporizador = setTimeout(cargar, CADA_MS)
        }
      } catch (error) {
        if (control.signal.aborted) return
        const mensaje = error instanceof Error ? error.message : "No se pudo cargar el informe."
        setFase({ tipo: "error", mensaje, reintentable: error instanceof ErrorApi && (error.sinConexion || error.estado >= 500) })
      }
    }
    void cargar()
    return () => {
      control.abort()
      clearTimeout(temporizador)
    }
  }, [id, intento, setSeccion])

  const nombreVideo = fase.tipo === "listo" || fase.tipo === "esperando" ? fase.estado.nombre_video : null
  useEffect(() => {
    document.title = nombreVideo ? `Informe de ${nombreVideo} · Detección de logos` : "Informe · Detección de logos"
  }, [nombreVideo])

  const contenedor = "mx-auto flex max-w-[1280px] flex-col gap-12 px-[clamp(24px,5vw,80px)] pt-12 pb-20"

  if (fase.tipo === "cargando") {
    return (
      <div className={contenedor}>
        <p className="etiqueta-datos m-0" role="status">
          Cargando el informe…
        </p>
      </div>
    )
  }

  if (fase.tipo === "error") {
    return (
      <div className={contenedor}>
        <h1 className="m-0 font-titular text-[clamp(40px,5vw,64px)] leading-none font-black">Informe</h1>
        <BloqueError mensaje={fase.mensaje}>
          {fase.reintentable && (
            <Button variant="invertido" onClick={() => setIntento((n) => n + 1)}>
              Reintentar
            </Button>
          )}
          <Link to="/analisis" viewTransition className={buttonVariants({ variant: "invertido" })}>
            Analizar otro vídeo
          </Link>
        </BloqueError>
      </div>
    )
  }

  if (fase.tipo === "esperando") {
    const porcentaje = Math.round(fase.estado.progreso * 100)
    return (
      <div className={contenedor}>
        <h1 className="m-0 font-titular text-[clamp(40px,5vw,64px)] leading-none font-black">Todavía no ha terminado.</h1>
        <div className="flex max-w-[640px] flex-col gap-3.5 bg-negro p-6 text-amarillo">
          <div className="etiqueta-datos flex justify-between gap-4">
            <span className="break-all">{fase.estado.nombre_video}</span>
            <span>{porcentaje} %</span>
          </div>
          <Progress value={porcentaje} aria-label="Progreso del análisis" />
          <p className="m-0" aria-live="polite">
            El informe aparecerá aquí en cuanto termine el análisis.
          </p>
        </div>
      </div>
    )
  }

  return <InformeListo key={id} id={id} {...fase} />
}

function InformeListo({
  id,
  estado,
  informe,
  detecciones,
}: {
  id: string
  estado: EstadoAnalisis
  informe: DatosInforme
  detecciones: DeteccionGuardada[]
}) {
  const enVivo = estado.modo === "en_vivo"
  const hayMarcas = informe.marcas.length > 0
  const grupos = useMemo(() => agrupar(detecciones, estado.intervalo_s), [detecciones, estado.intervalo_s])
  const tramos = useMemo(() => tramosPorMarca(grupos), [grupos])
  const modo = enVivo ? "en vivo" : "modo informe"

  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-12 px-[clamp(24px,5vw,80px)] pt-12 pb-20">
      <section className="flex flex-col gap-5">
        <p className="etiqueta-datos m-0 break-words">
          Informe · {estado.nombre_video} · {numero(estado.duracion_s)} s · umbral {numero(estado.umbral, 3)} · {modo}
        </p>
        <Titular hallazgos={informe.hallazgos} />
        <Resumen informe={informe} />
      </section>

      {hayMarcas && <Cifras marca={informe.marcas[0]} />}

      {hayMarcas && (
        <section className="flex flex-wrap gap-10">
          <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-3.5">
            <h2 className="m-0 font-titular text-[32px] font-black">El vídeo, con sus detecciones</h2>
            <VideoDelInforme id={id} estado={estado} grupos={grupos} enVivo={enVivo} />
            <LineaTiempo marcas={informe.marcas} tramos={tramos} duracion={estado.duracion_s} />
          </div>
          <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-3.5">
            <h2 className="m-0 font-titular text-[32px] font-black">Tiempo por marca</h2>
            <TablaMarcas marcas={informe.marcas} />
            <BarrasMarcas marcas={informe.marcas} />
          </div>
        </section>
      )}

      {hayMarcas && <Galeria detecciones={detecciones} />}

      <Link
        to={enVivo ? "/en-vivo" : "/analisis"}
        viewTransition
        className={buttonVariants({ size: "lg", className: "self-start" })}
      >
        Analizar otro vídeo
      </Link>
    </div>
  )
}

/**
 * El vídeo con las cajas, si el archivo sigue cargado en la página. Si se recargó, se
 * ofrece volver a elegirlo. La dirección del archivo se libera al salir del informe.
 */
function VideoDelInforme({
  id,
  estado,
  grupos,
  enVivo,
}: {
  id: string
  estado: EstadoAnalisis
  grupos: ReturnType<typeof agrupar>
  enVivo: boolean
}) {
  const { archivoDe, guardarArchivo } = useApp()
  const archivo = archivoDe(id)
  const [url, setUrl] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  useEffect(() => {
    if (!archivo) return
    const direccion = URL.createObjectURL(archivo)
    setUrl(direccion)
    return () => {
      URL.revokeObjectURL(direccion)
      setUrl(null)
    }
  }, [archivo])

  const elegir = async (nuevo: File) => {
    const duracion = await leerDuracion(nuevo)
    if (duracion === null) setAviso("Este navegador no puede reproducir ese archivo. El resto del informe se muestra igual.")
    else if (Math.abs(duracion - estado.duracion_s) > 0.5)
      setAviso(`Este archivo dura ${numero(duracion)} s y el analizado ${numero(estado.duracion_s)} s. Puede que no sea el mismo vídeo.`)
    else setAviso(null)
    if (duracion !== null) guardarArchivo(id, nuevo)
  }

  return (
    <div className="flex flex-col gap-3">
      {url ? (
        <VideoConCajas src={url} grupos={grupos} enVivo={enVivo} />
      ) : (
        <ZonaSubida
          alElegir={elegir}
          titulo="Vuelve a elegir el vídeo"
          className="min-h-[220px] bg-pista"
          descripcion="explicacion-video"
        />
      )}
      <p id="explicacion-video" className="m-0 font-datos text-xs leading-relaxed" role={aviso ? "status" : undefined}>
        {aviso ?? (url ? null : `El vídeo no está cargado en esta página. Elige ${estado.nombre_video} para verlo con sus cajas.`)}
      </p>
    </div>
  )
}
