"""Prueba de detección de logos en vídeo en tiempo real con el modelo en local.

Reproduce un vídeo en una ventana y dibuja encima las marcas que detecta best.onnx.
Para no frenar la reproducción, analiza un fotograma cada cierto tiempo y mantiene
las cajas en pantalla hasta el siguiente análisis.

Uso:
    python scripts/video_en_vivo.py RUTA_DEL_VIDEO
    python scripts/video_en_vivo.py RUTA_DEL_VIDEO --conf 0.5 --cada 0.2
    python scripts/video_en_vivo.py RUTA_DEL_VIDEO --guardar salida.mp4 --sin-ventana

Teclas en la ventana:  q = salir   espacio = pausa
"""

import argparse
import ast
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

TAMANO = 640
IOU_NMS = 0.7
RAIZ = Path(__file__).resolve().parent.parent
MODELO_POR_DEFECTO = RAIZ / "api" / "best.onnx"


class Detector:
    """Carga best.onnx y detecta logos en una imagen BGR. Misma lógica que api/main.py."""

    def __init__(self, ruta_modelo: Path):
        self.sesion = ort.InferenceSession(str(ruta_modelo), providers=["CPUExecutionProvider"])
        self.entrada = self.sesion.get_inputs()[0].name
        self.nombres = ast.literal_eval(self.sesion.get_modelmeta().custom_metadata_map["names"])

    def detectar(self, imagen: np.ndarray, conf: float) -> list[dict]:
        alto, ancho = imagen.shape[:2]
        escala = min(TAMANO / alto, TAMANO / ancho)
        nw, nh = round(ancho * escala), round(alto * escala)
        px, py = (TAMANO - nw) // 2, (TAMANO - nh) // 2
        lienzo = np.full((TAMANO, TAMANO, 3), 114, dtype=np.uint8)
        lienzo[py:py + nh, px:px + nw] = cv2.resize(imagen, (nw, nh), interpolation=cv2.INTER_LINEAR)

        entrada = lienzo[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        salida = self.sesion.run(None, {self.entrada: entrada})[0][0].T

        puntuaciones = salida[:, 4:]
        clases = puntuaciones.argmax(axis=1)
        confianzas = puntuaciones[np.arange(len(clases)), clases]
        mantener = confianzas >= conf
        if not mantener.any():
            return []
        cajas, clases, confianzas = salida[mantener, :4], clases[mantener], confianzas[mantener]

        xywh = cajas.copy()
        xywh[:, 0] -= xywh[:, 2] / 2
        xywh[:, 1] -= xywh[:, 3] / 2
        desplazadas = xywh.copy()
        desplazadas[:, :2] += clases[:, None] * 4096
        indices = np.array(cv2.dnn.NMSBoxes(desplazadas.tolist(), confianzas.tolist(), conf, IOU_NMS)).flatten()

        resultado = []
        for i in indices:
            x, y, w, h = xywh[i]
            resultado.append({
                "marca": self.nombres[int(clases[i])],
                "confianza": float(confianzas[i]),
                "caja": [
                    int(np.clip((x - px) / escala, 0, ancho)),
                    int(np.clip((y - py) / escala, 0, alto)),
                    int(np.clip((x + w - px) / escala, 0, ancho)),
                    int(np.clip((y + h - py) / escala, 0, alto)),
                ],
            })
        return resultado


def color_de(marca: str) -> tuple[int, int, int]:
    """Un color fijo y distinto para cada marca."""
    semilla = sum(ord(c) for c in marca)
    return (50 + semilla * 37 % 200, 50 + semilla * 91 % 200, 50 + semilla * 53 % 200)


def dibujar(fotograma: np.ndarray, detecciones: list[dict]) -> None:
    for d in detecciones:
        x1, y1, x2, y2 = d["caja"]
        color = color_de(d["marca"])
        texto = f'{d["marca"]} {d["confianza"]:.2f}'
        cv2.rectangle(fotograma, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(fotograma, (x1, max(y1 - th - 8, 0)), (x1 + tw + 6, max(y1, th + 8)), color, -1)
        cv2.putText(fotograma, texto, (x1 + 3, max(y1 - 5, th + 3)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)


def main() -> None:
    p = argparse.ArgumentParser(description="Detección de logos en vídeo en tiempo real (modelo local)")
    p.add_argument("video", type=Path, help="Ruta del vídeo")
    p.add_argument("--modelo", type=Path, default=MODELO_POR_DEFECTO, help="Ruta de best.onnx")
    p.add_argument("--conf", type=float, default=0.25, help="Umbral de confianza")
    p.add_argument("--cada", type=float, default=0.2,
                   help="Segundos de vídeo entre dos análisis (0.2 = 5 análisis por segundo)")
    p.add_argument("--guardar", type=Path, help="Guarda el vídeo con las cajas en esta ruta")
    p.add_argument("--sin-ventana", action="store_true", help="No abre ventana (solo para --guardar)")
    args = p.parse_args()

    detector = Detector(args.modelo)
    video = cv2.VideoCapture(str(args.video))
    if not video.isOpened():
        raise SystemExit(f"No se pudo abrir el vídeo {args.video}")
    fps = video.get(cv2.CAP_PROP_FPS) or 30
    ancho = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    escritor = None
    if args.guardar:
        escritor = cv2.VideoWriter(str(args.guardar), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ancho, alto))

    detecciones: list[dict] = []
    ultimo_analisis = -1e9
    tiempos_ms: list[float] = []
    numero = 0
    saltados = 0
    inicio_real = time.perf_counter()

    while True:
        # Si vamos atrasados respecto al reloj real, saltar fotogramas sin procesarlos
        if not args.sin_ventana:
            objetivo = int((time.perf_counter() - inicio_real) * fps)
            while numero < objetivo - 1 and video.grab():
                numero += 1
                saltados += 1
        ok, fotograma = video.read()
        if not ok:
            break
        segundo_video = numero / fps

        # Analizar solo cada --cada segundos de vídeo; en medio se mantienen las últimas cajas
        if segundo_video - ultimo_analisis >= args.cada:
            t0 = time.perf_counter()
            detecciones = detector.detectar(fotograma, args.conf)
            tiempos_ms.append((time.perf_counter() - t0) * 1000)
            ultimo_analisis = segundo_video

        dibujar(fotograma, detecciones)
        info = f"t={segundo_video:5.1f}s  modelo={tiempos_ms[-1]:.0f} ms" if tiempos_ms else ""
        cv2.putText(fotograma, info, (10, alto - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        if escritor:
            escritor.write(fotograma)
        if not args.sin_ventana:
            factor = min(1.0, 900 / ancho)
            cv2.imshow("Deteccion de logos (q para salir)", cv2.resize(fotograma, None, fx=factor, fy=factor))
            # Esperar lo necesario para reproducir a la velocidad real del vídeo
            retraso = (numero + 1) / fps - (time.perf_counter() - inicio_real)
            tecla = cv2.waitKey(max(1, int(retraso * 1000))) & 0xFF
            if tecla == ord("q"):
                break
            if tecla == ord(" "):
                pausa = time.perf_counter()
                while (cv2.waitKey(50) & 0xFF) != ord(" "):
                    pass
                inicio_real += time.perf_counter() - pausa
        numero += 1

    video.release()
    if escritor:
        escritor.release()
    cv2.destroyAllWindows()

    duracion_real = time.perf_counter() - inicio_real
    if tiempos_ms:
        print(f"Fotogramas mostrados: {numero} ({numero / fps:.1f} s de vídeo a {fps:.0f} fps)")
        print(f"Tiempo real de reproducción: {duracion_real:.1f} s")
        print(f"Fotogramas saltados para no atrasarse: {saltados}")
        print(f"Análisis hechos: {len(tiempos_ms)}, tiempo medio del modelo: {np.mean(tiempos_ms):.0f} ms")
        if duracion_real > numero / fps * 1.1:
            print("Aviso: la reproducción fue más lenta que el vídeo. Prueba con un --cada mayor.")


if __name__ == "__main__":
    main()