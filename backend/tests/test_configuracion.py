"""Lectura de variables de entorno y normalización de la cadena de conexión."""

import secrets
from pathlib import Path

import pytest

from basedatos import normalizar_url
from config import CARPETA_BACKEND, Ajustes

VARIABLES = (
    "MODEL_API_URL", "MODEL_API_KEY", "DATABASE_URL", "MODOS",
    "FRONT_ORIGIN", "MOSTRAR_DOCS", "LIMITE_EN_VIVO_POR_MINUTO",
)


def _entorno(monkeypatch, **valores):
    base = {
        "MODEL_API_URL": "http://api.prueba",
        "MODEL_API_KEY": secrets.token_hex(8),
        "DATABASE_URL": "sqlite:///prueba.db",
        "MODOS": "informe",
    }
    base.update(valores)
    for nombre in VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    for nombre, valor in base.items():
        if valor is not None:
            monkeypatch.setenv(nombre, valor)


@pytest.mark.parametrize("variable", ["MODEL_API_URL", "MODEL_API_KEY", "DATABASE_URL", "MODOS"])
def test_no_arranca_sin_una_variable_obligatoria(monkeypatch, variable):
    _entorno(monkeypatch, **{variable: None})
    with pytest.raises(RuntimeError, match=variable):
        Ajustes.desde_entorno()


def test_valores_por_defecto_seguros(monkeypatch):
    _entorno(monkeypatch)
    ajustes = Ajustes.desde_entorno()
    assert ajustes.mostrar_docs is False
    assert ajustes.front_origin is None
    assert ajustes.limite_en_vivo_por_minuto == 30
    assert ajustes.modos == ("informe",)
    assert ajustes.en_vivo is False


def test_lee_modos_limite_docs_y_origen(monkeypatch):
    _entorno(
        monkeypatch, MODOS=" en_vivo , informe ", LIMITE_EN_VIVO_POR_MINUTO="600",
        MOSTRAR_DOCS="1", FRONT_ORIGIN="http://localhost:5173/", MODEL_API_URL="https://api.prueba/",
    )
    ajustes = Ajustes.desde_entorno()
    assert ajustes.modos == ("informe", "en_vivo")
    assert ajustes.en_vivo is True
    assert ajustes.limite_en_vivo_por_minuto == 600
    assert ajustes.mostrar_docs is True
    assert ajustes.front_origin == "http://localhost:5173"
    assert ajustes.model_api_url == "https://api.prueba"


@pytest.mark.parametrize("valores", [
    {"MODOS": "informe,otro"},
    {"MODOS": ","},
    {"LIMITE_EN_VIVO_POR_MINUTO": "0"},
    {"LIMITE_EN_VIVO_POR_MINUTO": "muchos"},
    {"MODEL_API_URL": "ftp://api.prueba"},
    {"FRONT_ORIGIN": "*"},
])
def test_rechaza_valores_no_validos(monkeypatch, valores):
    _entorno(monkeypatch, **valores)
    with pytest.raises(RuntimeError):
        Ajustes.desde_entorno()


def test_la_clave_y_la_cadena_de_conexion_no_salen_en_el_repr(monkeypatch):
    clave, contrasena = secrets.token_hex(16), secrets.token_hex(16)
    _entorno(
        monkeypatch, MODEL_API_KEY=clave,
        DATABASE_URL=f"postgresql://usuario:{contrasena}@servidor/bd",
    )
    texto = repr(Ajustes.desde_entorno())
    assert clave not in texto
    assert contrasena not in texto


def test_normaliza_las_direcciones_de_render_y_sqlite():
    assert normalizar_url("postgres://servidor/bd").drivername == "postgresql+psycopg"
    assert normalizar_url("postgresql://servidor/bd").drivername == "postgresql+psycopg"
    assert normalizar_url("postgresql+psycopg://servidor/bd").drivername == "postgresql+psycopg"
    assert Path(normalizar_url("sqlite:///data/logos.db").database) == CARPETA_BACKEND / "data" / "logos.db"
    assert normalizar_url("sqlite:///:memory:").database == ":memory:"
