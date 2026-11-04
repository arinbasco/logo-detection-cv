"""Preparación común de los tests.

Entorno falso, base de datos SQLite temporal con las migraciones aplicadas, API del modelo
simulada y vídeos de prueba generados en el momento. Ningún test llama a la API real ni
lee el archivo .env.
"""

import os
import secrets

import dotenv

# Los tests nunca leen el .env real: se anula su carga antes de importar el backend
dotenv.load_dotenv = lambda *args, **kwargs: False

# Clave inventada en cada ejecución, para que ningún valor parecido a una clave quede escrito
CLAVE_FALSA = "prueba-" + secrets.token_hex(16)
os.environ.update({
    "MODEL_API_URL": "http://api-modelo.prueba",
    "MODEL_API_KEY": CLAVE_FALSA,
    "DATABASE_URL": "sqlite:///:memory:",
    "MODOS": "informe,en_vivo",
    "MOSTRAR_DOCS": "0",
    "FRONT_ORIGIN": "http://front.prueba",
})
os.environ.pop("LIMITE_EN_VIVO_POR_MINUTO", None)

import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

import imagenes  # noqa: E402,F401  fija el límite de píxeles de OpenCV antes de importar cv2
import cv2  # noqa: E402
import httpx  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from config import CARPETA_BACKEND, Ajustes  # noqa: E402

MARCAS = [
    "Adidas", "Apple Inc-", "Chanel", "Coca-Cola", "Emirates", "Hard Rock Cafe", "Mercedes-Benz",
    "NFL", "Nike", "Pepsi", "Puma", "Starbucks", "The North Face", "Toyota", "Under Armour",
]


def _imagen_del_formulario(request: httpx.Request) -> np.ndarray:
    limite = request.headers["content-type"].split("boundary=")[1].encode()
    for parte in request.read().split(b"--" + limite):
        if b'name="imagen"' in parte:
            contenido = parte.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
            return cv2.imdecode(np.frombuffer(contenido, np.uint8), cv2.IMREAD_COLOR)
    raise AssertionError("La petición no traía el campo imagen")


class ApiModeloSimulada:
    """Imita la API del modelo: GET / con las marcas y POST /predict con respuestas guionizadas.

    Cada elemento del guion es la respuesta de una llamada a /predict: una lista de
    detecciones o uno de los fallos "sin_respuesta", "error" o "formato_raro". Cuando el
    guion se acaba se usa por_defecto.
    """

    def __init__(self):
        self.guion: list = []
        self.por_defecto: list | str = []
        self.imagenes_recibidas: list[tuple[int, int]] = []
        self.umbrales_recibidos: list[float] = []
        self.claves_recibidas: list[str | None] = []
        self.fallar_estado = False
        self.permisos: threading.Semaphore | None = None  # si existe, cada /predict espera uno
        self._candado = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.claves_recibidas.append(request.headers.get("x-api-key"))
        if request.url.path == "/":
            if self.fallar_estado:
                raise httpx.ConnectError("fallo simulado", request=request)
            return httpx.Response(200, json={"estado": "ok", "modelo": "best.onnx", "marcas": MARCAS})
        if request.url.path != "/predict":
            return httpx.Response(404)
        imagen = _imagen_del_formulario(request)
        if self.permisos is not None:
            assert self.permisos.acquire(timeout=10), "El test no dio permiso a tiempo"
        with self._candado:
            self.imagenes_recibidas.append((imagen.shape[1], imagen.shape[0]))
            self.umbrales_recibidos.append(float(request.url.params["conf"]))
            accion = self.guion.pop(0) if self.guion else self.por_defecto
        if accion == "sin_respuesta":
            raise httpx.ReadTimeout("fallo simulado", request=request)
        if accion == "error":
            return httpx.Response(500, json={"detail": "fallo simulado"})
        if accion == "formato_raro":
            return httpx.Response(200, json={"resultado": "inesperado"})
        alto, ancho = imagen.shape[:2]
        return httpx.Response(200, json={"ancho": ancho, "alto": alto, "conf": 0.5, "detecciones": accion})

    @property
    def llamadas_predict(self) -> int:
        return len(self.imagenes_recibidas)


@pytest.fixture
def api_modelo() -> ApiModeloSimulada:
    return ApiModeloSimulada()


@pytest.fixture
def url_bd(tmp_path, monkeypatch) -> str:
    """Base de datos SQLite temporal con las migraciones de Alembic aplicadas."""
    url = f"sqlite:///{(tmp_path / 'prueba.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    configuracion = Config(str(CARPETA_BACKEND / "alembic.ini"))
    configuracion.attributes["configurar_registros"] = False
    command.upgrade(configuracion, "head")
    return url


@pytest.fixture
def carpeta_temporal(tmp_path):
    return tmp_path / "temporal"


@pytest.fixture
def crear_cliente(url_bd, api_modelo, carpeta_temporal):
    """Fabrica clientes de prueba con la app arrancada y la API del modelo simulada."""
    abiertos: list[TestClient] = []

    def _crear(lanzar_errores: bool = True, **cambios) -> TestClient:
        valores = {
            "model_api_url": "http://api-modelo.prueba",
            "model_api_key": CLAVE_FALSA,
            "database_url": url_bd,
            "modos": ("informe", "en_vivo"),
            "front_origin": "http://front.prueba",
            "mostrar_docs": False,
        }
        valores.update(cambios)
        app = main.crear_app(Ajustes(**valores), httpx.MockTransport(api_modelo), carpeta_temporal)
        cliente = TestClient(app, raise_server_exceptions=lanzar_errores)
        cliente.__enter__()
        abiertos.append(cliente)
        return cliente

    yield _crear
    if api_modelo.permisos is not None:
        api_modelo.permisos.release(1000)
    for cliente in abiertos:
        cliente.app.state.contexto.gestor.esperar(30)
        cliente.__exit__(None, None, None)


@pytest.fixture
def cliente(crear_cliente) -> TestClient:
    return crear_cliente()


@pytest.fixture
def crear_video(tmp_path):
    """Genera con OpenCV un vídeo de prueba y devuelve sus bytes."""

    def _crear(segundos: float = 10, fps: int = 10, ancho: int = 160, alto: int = 120,
               extension: str = ".mp4", fourcc: str = "mp4v") -> bytes:
        ruta = tmp_path / f"video_{uuid.uuid4().hex}{extension}"
        escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*fourcc), fps, (ancho, alto))
        assert escritor.isOpened(), "OpenCV no pudo crear el vídeo de prueba"
        for i in range(round(segundos * fps)):
            fotograma = np.full((alto, ancho, 3), 40, np.uint8)
            cv2.rectangle(fotograma, (0, 0), (ancho // 3, alto // 3), (0, (i * 5) % 255, 200), -1)
            escritor.write(fotograma)
        escritor.release()
        datos = ruta.read_bytes()
        ruta.unlink()
        return datos

    return _crear


def subir_video(cliente: TestClient, datos: bytes, nombre: str = "video.mp4", **campos):
    return cliente.post(
        "/analisis",
        files={"video": (nombre, datos, "application/octet-stream")},
        data={clave: str(valor) for clave, valor in campos.items()},
    )


@pytest.fixture
def subir():
    return subir_video


def crear_imagen(ancho: int, alto: int, formato: str = ".jpg") -> bytes:
    """Imagen gris codificada, como un fotograma que captura el front."""
    return cv2.imencode(formato, np.full((alto, ancho, 3), 90, np.uint8))[1].tobytes()


def _formulario(campos: dict) -> dict:
    """Campos de formulario como texto. Los que valen None no se envían."""
    return {clave: str(valor) for clave, valor in campos.items() if valor is not None}


def abrir_sesion(cliente: TestClient, **campos):
    """Abre una sesión en vivo. Sin más campos, para un vídeo de 60 segundos."""
    return cliente.post("/en-vivo/sesion", data=_formulario({"nombre_video": "video.mp4", "duracion_s": 60, **campos}))


def enviar_fotograma(cliente: TestClient, sesion_id: str | None, datos: bytes, nombre: str = "fotograma.jpg",
                     headers=None, **campos):
    return cliente.post(
        "/en-vivo/fotograma",
        files={"imagen": (nombre, datos, "application/octet-stream")},
        data=_formulario({"sesion_id": sesion_id, "t_s": 1.5, **campos}),
        headers=headers,
    )


@pytest.fixture
def esperar_analisis():
    """Espera a que termine el análisis en curso y devuelve su estado final."""

    def _esperar(cliente: TestClient, analisis_id: str) -> dict:
        assert cliente.app.state.contexto.gestor.esperar(30), "El análisis no terminó a tiempo"
        return cliente.get(f"/analisis/{analisis_id}").json()

    return _esperar


@pytest.fixture
def esperar_progreso():
    """Espera, sin llamar a la API, a que el análisis haya procesado n fotogramas."""

    def _esperar(cliente: TestClient, analisis_id: str, procesados: int, total: int) -> None:
        from modelos import Analisis

        fin = time.monotonic() + 10
        while time.monotonic() < fin:
            with cliente.app.state.contexto.sesiones() as sesion:
                analisis = sesion.get(Analisis, uuid.UUID(analisis_id))
                if round(analisis.progreso * total) >= procesados:
                    return
            time.sleep(0.02)
        raise AssertionError("El análisis no avanzó a tiempo")

    return _esperar
