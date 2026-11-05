import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode, type SyntheticEvent } from "react"
import { useNavigate } from "react-router"
import { PauseIcon, PlayIcon } from "@phosphor-icons/react"

import { api, ErrorApi, type RespuestaEnVivo } from "@/api/cliente"
import { BloqueError } from "@/components/BloqueError"
import { Button } from "@/components/ui/button"
import { CapaCajas, type CajaVisible } from "@/components/video/CapaCajas"
import { useAreaVideo } from "@/components/video/medidas"
import { Grano, Reproductor } from "@/components/video/Reproductor"
import { ZonaSubida } from "@/components/ZonaSubida"
import { useApp } from "@/estado/app"
import { useEstable } from "@/hooks/estable"
import { DURACION_MAXIMA_S, VIDEO_LARGO } from "@/lib/archivos"
import { tamanoEnVivo } from "@/lib/cajas"
import { capturar, segundosHastaAhora, type FotogramaAnalizado } from "@/lib/enVivo"
import { confianza, nombreMarca, numero, reloj } from "@/lib/formato"
import { cn } from "@/lib/utils"

const ESPERA_TRAS_429_MS = 5000 // límite de fotogramas por minuto: se espera y se sigue
const ESPERA_TRAS_FALLO_MS = 3000
const ULTIMAS = 6
const NO_REPRODUCIBLE = "Este navegador no puede reproducir ese vídeo. Prueba con un MP4 (H.264) o un WEBM."

const esperar = (ms: number) => new Promise((resolver) => setTimeout(resolver, ms))

interface Deteccion {
  t_s: number
  marca: string
  confianza: number
}

export function EnVivo() {
  const { enVivoDisponible } = useApp()

  useEffect(() => {
    document.title = "En vivo · Detección de logos"
  }, [])

  return (
    <div className="composicion gap-8">
      {enVivoDisponible ? <EnVivoLocal /> : <EnVivoDesactivado />}
    </div>
  )
}

function Indicador({ texto, grabando }: { texto: string; grabando: boolean }) {
  return (
    <span className="etiqueta-datos inline-flex items-center gap-2 tracking-[0.06em]" aria-live="polite">
      <span
        className={cn("size-2.5 rounded-full", grabando ? "bg-grabando" : "border-2 border-negro")}
        aria-hidden="true"
      />
      {texto}
    </span>
  )
}

function Cabeza({ indicador }: { indicador: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-4">
      <h1 className="m-0 font-titular text-cabeza leading-none font-black">En vivo.</h1>
      {indicador}
    </div>
  )
}

function HastaAhora({ totales }: { totales: Array<{ marca: string; segundos: number }> }) {
  const maximo = Math.max(...totales.map((t) => t.segundos), 0)
  return (
    <div className="flex flex-col gap-4 bg-negro p-6 text-amarillo">
      <h2 className="m-0 font-titular text-rotulo font-black">Hasta ahora</h2>
      {totales.length === 0 ? (
        <p className="m-0 text-base">Todavía no hay ninguna marca en pantalla.</p>
      ) : (
        totales.map(({ marca, segundos }) => (
          <div key={marca} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-4 font-semibold">
              <span>{nombreMarca(marca)}</span>
              <span className="font-datos">{numero(segundos).includes(",") ? numero(segundos) : `${numero(segundos)},0`} s</span>
            </div>
            <div className="h-2 bg-amarillo/25" aria-hidden="true">
              <div className="h-2 bg-amarillo" style={{ width: `${maximo ? (segundos / maximo) * 100 : 0}%` }} />
            </div>
          </div>
        ))
      )}
      <p className="m-0 font-datos text-xs leading-relaxed text-amarillo-tenue">
        Cada fotograma tarda unas décimas de segundo en local. Las cajas llegan con ese retraso.
      </p>
    </div>
  )
}

function UltimasDetecciones({ detecciones }: { detecciones: Deteccion[] }) {
  return (
    <div className="flex flex-col gap-2">
      <h2 className="etiqueta-datos m-0 text-xs tracking-[0.06em]">Últimas detecciones</h2>
      {detecciones.length === 0 ? (
        <p className="m-0 border-b-2 border-negro py-2.5 font-datos text-sm">Ninguna todavía.</p>
      ) : (
        <ul role="list" className="m-0 list-none p-0">
          {detecciones.map((d, i) => (
            <li key={`${d.t_s}-${d.marca}-${i}`} className="flex justify-between gap-4 border-b-2 border-negro py-2.5 font-datos text-sm">
              <span>
                {reloj(d.t_s, true)} · {nombreMarca(d.marca)}
              </span>
              <span>{confianza(d.confianza)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Versión nube: la página se ve con su diseño, pero el reproductor está desactivado. */
function EnVivoDesactivado() {
  const demo = import.meta.env.VITE_VIDEO_DEMO_URL
  return (
    <>
      <section className="flex min-w-0 flex-[999_1_calc(var(--u)*640)] flex-col gap-4">
        <Cabeza indicador={<Indicador texto="Solo en la versión local" grabando={false} />} />
        <div className="relative aspect-video overflow-hidden bg-negro">
          {demo ? (
            <video
              src={demo}
              controls
              muted
              loop
              playsInline
              className="absolute inset-0 h-full w-full object-contain"
              aria-label="Vídeo grabado de la demo del modo en vivo en la versión local"
            />
          ) : (
            <p className="absolute right-6 bottom-5 left-6 m-0 font-datos text-aviso text-[#bdbdbd]">
              [ El análisis en vivo funciona en la versión local, con la API del modelo en el propio ordenador ]
            </p>
          )}
        </div>
        <div className="flex items-center gap-4" aria-hidden="true">
          <span className="inline-flex size-12 items-center justify-center bg-negro opacity-40">
            <PlayIcon weight="fill" className="size-5 text-amarillo" />
          </span>
          <div className="h-2 flex-auto bg-negro/20" />
          <span className="font-datos text-sm">00:00 / 00:00</span>
        </div>
      </section>
      <aside className="flex flex-[1_1_calc(var(--u)*300)] flex-col gap-5">
        <div role="note" className="flex flex-col gap-3 bg-negro p-6 text-amarillo">
          <h2 className="m-0 font-titular text-rotulo font-black">Solo en local</h2>
          <p className="m-0 text-base leading-normal">
            El modo en vivo solo funciona en la versión local. En esta versión publicada puedes analizar un vídeo
            completo en Análisis.
          </p>
        </div>
        <Button disabled className="w-full" size="lg">
          Terminar y ver el informe
        </Button>
        <p className="m-0 text-aviso leading-normal">
          En la versión publicada esta página se muestra, pero el análisis en vivo solo funciona en la versión local.
        </p>
      </aside>
    </>
  )
}

/** Versión local: analiza el vídeo mientras se reproduce, un fotograma cada vez. */
function EnVivoLocal() {
  const { guardarArchivo } = useApp()
  const navegar = useNavigate()
  const [archivo, setArchivo] = useState<File | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [video, setVideo] = useState<HTMLVideoElement | null>(null)
  const [sesion, setSesion] = useState<string | null>(null)
  const [preparando, setPreparando] = useState(false)
  const [reproduciendo, setReproduciendo] = useState(false)
  const [tiempo, setTiempo] = useState({ actual: 0, total: 0 })
  const [ultima, setUltima] = useState<RespuestaEnVivo | null>(null)
  const [fotogramas, setFotogramas] = useState<FotogramaAnalizado[]>([])
  const [ultimas, setUltimas] = useState<Deteccion[]>([])
  const [aviso, setAviso] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [terminando, setTerminando] = useState(false)

  const peticion = useRef<Promise<unknown> | null>(null)
  const salir = useRef<AbortController | null>(null)
  const medidas = useAreaVideo(video)

  // La dirección del archivo local se libera al cambiar de vídeo o salir de la página
  useEffect(() => {
    if (!archivo) return
    const direccion = URL.createObjectURL(archivo)
    setUrl(direccion)
    return () => URL.revokeObjectURL(direccion)
  }, [archivo])

  // Al salir de la página se cancela la petición en curso. Se crea aquí y no en el useRef:
  // así un montaje doble, como el de StrictMode, no deja el controlador ya abortado
  useEffect(() => {
    const control = new AbortController()
    salir.current = control
    return () => control.abort()
  }, [])

  const elegir = (nuevo: File) => {
    video?.pause()
    setArchivo(nuevo)
    setSesion(null)
    setUltima(null)
    setFotogramas([])
    setUltimas([])
    setAviso(null)
    setError(null)
  }

  const aplicar = useCallback((respuesta: RespuestaEnVivo) => {
    setUltima(respuesta)
    setFotogramas((anteriores) => [...anteriores, { t_s: respuesta.t_s, marcas: respuesta.detecciones.map((d) => d.marca) }])
    if (respuesta.detecciones.length) {
      const nuevas = respuesta.detecciones.map((d) => ({ t_s: respuesta.t_s, marca: d.marca, confianza: d.confianza }))
      setUltimas((anteriores) => [...nuevas, ...anteriores].slice(0, ULTIMAS))
    }
  }, [])

  // Mientras se reproduce: captura, envía, espera la respuesta y vuelve a empezar
  useEffect(() => {
    const senal = salir.current?.signal
    if (!video || !reproduciendo || !sesion || !senal) return
    let seguir = true
    const lienzo = document.createElement("canvas")
    const bucle = async () => {
      // Si se pausó y se reanudó deprisa, se espera a la petición anterior: solo una en curso
      await peticion.current?.catch(() => {})
      while (seguir && !video.paused && !video.ended) {
        const t_s = Math.round(Math.min(video.currentTime, video.duration) * 1000) / 1000
        try {
          const envio = capturar(video, lienzo).then((imagen) => api.enviarFotograma(sesion, imagen, t_s, senal))
          peticion.current = envio
          const respuesta = await envio
          aplicar(respuesta) // también cuenta si se pausó mientras se analizaba
          if (!seguir) return
          setAviso(null)
        } catch (fallo) {
          if (senal.aborted) return
          if (fallo instanceof ErrorApi && fallo.estado === 429) {
            setAviso("Demasiados fotogramas por minuto. Espero unos segundos y sigo.")
            await esperar(ESPERA_TRAS_429_MS)
          } else if (fallo instanceof ErrorApi && (fallo.estado === 502 || fallo.sinConexion)) {
            setAviso(`${fallo.message} Lo vuelvo a intentar.`)
            await esperar(ESPERA_TRAS_FALLO_MS)
          } else {
            setError(fallo instanceof Error ? fallo.message : "No se pudo analizar el fotograma.")
            video.pause()
            return
          }
        }
      }
    }
    void bucle()
    return () => {
      seguir = false
    }
  }, [video, reproduciendo, sesion, aplicar])

  // Al pulsar reproducir por primera vez se crea la sesión con la duración del vídeo
  const alReproducir = useEstable(async () => {
    setReproduciendo(true)
    if (sesion || preparando || !video || !archivo) return
    if (video.duration > DURACION_MAXIMA_S) {
      video.pause()
      setError(VIDEO_LARGO)
      return
    }
    setPreparando(true)
    try {
      const creada = await api.crearSesion(archivo.name, Math.round(video.duration * 1000) / 1000)
      setSesion(creada.id)
    } catch (fallo) {
      video.pause()
      setError(fallo instanceof Error ? fallo.message : "No se pudo empezar la sesión.")
    } finally {
      setPreparando(false)
    }
  })

  const terminar = useEstable(async () => {
    if (!sesion || terminando || !archivo) return
    setTerminando(true)
    video?.pause()
    await peticion.current?.catch(() => {}) // el último fotograma enviado tiene que quedar guardado
    try {
      const estado = await api.cerrarSesion(sesion)
      if (estado.estado === "fallido") {
        setError(estado.error ?? "La sesión no tiene resultados.")
        setSesion(null)
        setTerminando(false)
        return
      }
      guardarArchivo(sesion, archivo)
      navegar(`/informe/${sesion}`, { viewTransition: true })
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : "No se pudo cerrar la sesión.")
      setTerminando(false)
    }
  })

  const alPausar = useCallback(() => setReproduciendo(false), [])
  const alCambiarTiempo = useCallback((evento: SyntheticEvent<HTMLVideoElement>) => {
    setTiempo({ actual: evento.currentTarget.currentTime, total: evento.currentTarget.duration || 0 })
  }, [])
  const alFallar = useCallback(() => setError(NO_REPRODUCIBLE), [])

  const alternar = () => {
    if (!video) return
    if (video.paused) void video.play().catch(() => setError(NO_REPRODUCIBLE))
    else video.pause()
  }

  const origen = useMemo(() => tamanoEnVivo(medidas.video), [medidas.video])
  const cajas = useMemo<CajaVisible[]>(
    () =>
      ultima?.detecciones.map((d, i) => ({
        clave: `${ultima.t_s}-${i}-${d.marca}`,
        marca: d.marca,
        confianza: d.confianza,
        caja: d.caja,
      })) ?? [],
    [ultima],
  )
  const totales = useMemo(() => segundosHastaAhora(fotogramas), [fotogramas])

  let estadoTexto = "Elige un vídeo para empezar"
  if (archivo) estadoTexto = "Pulsa reproducir para empezar"
  if (sesion && !reproduciendo) estadoTexto = "En pausa · no se envían fotogramas"
  if (preparando) estadoTexto = "Preparando la sesión…"
  if (sesion && reproduciendo) estadoTexto = "Analizando mientras se reproduce"
  if (terminando) estadoTexto = "Cerrando la sesión…"

  return (
    <>
      <section className="flex min-w-0 flex-[999_1_calc(var(--u)*640)] flex-col gap-4" aria-label="Reproductor">
        <Cabeza indicador={<Indicador texto={estadoTexto} grabando={Boolean(sesion && reproduciendo && !terminando)} />} />

        {!url ? (
          <ZonaSubida alElegir={elegir} titulo="Elige el vídeo que quieres ver" className="aspect-video min-h-0" descripcion="aviso-en-vivo" />
        ) : (
          <div className="relative aspect-video overflow-hidden bg-negro">
            <Reproductor
              src={url}
              alElemento={setVideo}
              aria-label="Vídeo analizado mientras se reproduce"
              onPlay={alReproducir}
              onPause={alPausar}
              onEnded={terminar}
              onTimeUpdate={alCambiarTiempo}
              onLoadedMetadata={alCambiarTiempo}
              onError={alFallar}
            />
            <Grano />
            {/* Antes que las cajas, para que sus etiquetas queden encima si coinciden. En móvil, abajo */}
            {ultima && (
              <span className="absolute right-3 bottom-3 bg-negro px-2.5 py-1.5 font-datos text-xs text-amarillo sm:top-4 sm:right-5 sm:bottom-auto">
                cajas del segundo {reloj(ultima.t_s, true)}
              </span>
            )}
            <CapaCajas cajas={cajas} origen={origen} area={medidas.area} contenedor={medidas.contenedor} />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={alternar}
            disabled={!url || terminando}
            aria-label={reproduciendo ? "Pausa" : "Reproducir"}
            className="inline-flex size-12 cursor-pointer items-center justify-center bg-negro text-amarillo disabled:cursor-not-allowed disabled:opacity-40"
          >
            {reproduciendo ? <PauseIcon weight="fill" className="size-5" /> : <PlayIcon weight="fill" className="size-5" />}
          </button>
          <input
            type="range"
            min={0}
            max={tiempo.total || 0}
            step={0.1}
            value={tiempo.actual}
            disabled={!url || terminando}
            aria-label="Posición en el vídeo"
            aria-valuetext={`${reloj(tiempo.actual)} de ${reloj(tiempo.total)}`}
            onChange={(evento) => {
              if (video) video.currentTime = Number(evento.target.value)
            }}
            className="barra-tiempo h-2 min-w-[calc(var(--u)*200)] flex-[1_1_calc(var(--u)*240)] cursor-pointer"
            style={{ "--avance": `${tiempo.total ? (tiempo.actual / tiempo.total) * 100 : 0}%` } as CSSProperties}
          />
          <span className="font-datos text-sm">
            {reloj(tiempo.actual)} / {reloj(tiempo.total)}
          </span>
          {url && (
            <ZonaSubidaCompacta alElegir={elegir} desactivada={terminando} />
          )}
        </div>

        {aviso && !error && (
          <p role="status" className="m-0 bg-negro px-4 py-3 font-datos text-sm text-amarillo">
            {aviso}
          </p>
        )}
        {error && (
          <BloqueError mensaje={error}>
            <Button variant="invertido" onClick={() => setError(null)}>
              Cerrar el aviso
            </Button>
          </BloqueError>
        )}
      </section>

      <aside className="flex flex-[1_1_calc(var(--u)*300)] flex-col gap-5">
        <HastaAhora totales={totales} />
        <UltimasDetecciones detecciones={ultimas} />
        <Button size="lg" className="w-full" onClick={terminar} disabled={!sesion} cargando={terminando}>
          Terminar y ver el informe
        </Button>
        <p id="aviso-en-vivo" className="m-0 text-aviso leading-normal">
          El vídeo se reproduce desde tu ordenador y no se sube entero: solo viajan los fotogramas que se analizan. En
          la versión publicada esta página se muestra, pero el análisis en vivo solo funciona en la versión local.
        </p>
      </aside>
    </>
  )
}

/** Botón para cambiar de vídeo sin salir de la página. */
function ZonaSubidaCompacta({ alElegir, desactivada }: { alElegir: (archivo: File) => void; desactivada: boolean }) {
  const entrada = useRef<HTMLInputElement>(null)
  return (
    <>
      <Button variant="outline" size="sm" disabled={desactivada} onClick={() => entrada.current?.click()}>
        Elegir otro vídeo
      </Button>
      <input
        ref={entrada}
        type="file"
        accept="video/*"
        className="hidden"
        tabIndex={-1}
        onChange={(evento) => {
          const nuevo = evento.target.files?.[0]
          evento.target.value = ""
          if (nuevo) alElegir(nuevo)
        }}
      />
    </>
  )
}
