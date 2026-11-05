/**
 * Cola de peticiones con un máximo en paralelo y otro por minuto.
 *
 * El backend admite 120 peticiones por minuto e IP en cada endpoint. La galería pide los
 * recortes por aquí para no pasar de ese límite aunque el usuario baje muy deprisa.
 */
export class Limitador {
  private enCurso = 0
  private readonly inicios: number[] = []
  private readonly cola: Array<() => void> = []
  private temporizador: ReturnType<typeof setTimeout> | null = null
  private readonly maximoEnParalelo: number
  private readonly maximoPorMinuto: number

  constructor(maximoEnParalelo: number, maximoPorMinuto: number) {
    this.maximoEnParalelo = maximoEnParalelo
    this.maximoPorMinuto = maximoPorMinuto
  }

  encolar<T>(tarea: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolver, rechazar) => {
      this.cola.push(() => {
        this.enCurso++
        this.inicios.push(Date.now())
        tarea()
          .then(resolver, rechazar)
          .finally(() => {
            this.enCurso--
            this.siguiente()
          })
      })
      this.siguiente()
    })
  }

  /** Descarta lo que aún no ha empezado, por ejemplo al salir del informe. */
  vaciar(): void {
    this.cola.length = 0
  }

  private siguiente(): void {
    const ahora = Date.now()
    while (this.inicios.length && ahora - this.inicios[0] >= 60_000) this.inicios.shift()
    while (this.cola.length && this.enCurso < this.maximoEnParalelo && this.inicios.length < this.maximoPorMinuto) {
      this.cola.shift()?.()
    }
    if (this.cola.length && this.inicios.length >= this.maximoPorMinuto && this.temporizador === null) {
      // Espera a que la petición más antigua salga de la ventana de un minuto
      this.temporizador = setTimeout(() => {
        this.temporizador = null
        this.siguiente()
      }, 60_000 - (ahora - this.inicios[0]) + 50)
    }
  }
}
