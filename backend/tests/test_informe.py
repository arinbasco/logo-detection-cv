"""Informe redactado: cifras justificadas, texto determinista, sin detecciones, nota final y modo en vivo."""

import random
import re

import pytest

from informe import construir_informe
from plantillas_informe import NOTA_FINAL


def _detecciones(por_marca: dict[str, list[int]], confianza: float = 0.9, intervalo: float = 1.0):
    return [(k * intervalo, marca, confianza) for marca, muestras in por_marca.items() for k in muestras]


def _en_vivo(duracion_s: float, fotogramas: list[float], detecciones, umbral: float = 0.775) -> dict:
    return dict(
        duracion_s=duracion_s, intervalo_s=None, umbral=umbral, fotogramas_analizados=len(fotogramas),
        detecciones=detecciones, fotogramas=fotogramas,
    )


def _resumen_sin_nota(informe: dict) -> str:
    return informe["resumen"].removesuffix(NOTA_FINAL).rstrip()


CASOS = {
    "dominante_concentracion_momento": dict(
        duracion_s=10.0, intervalo_s=1.0, umbral=0.775, fotogramas_analizados=10,
        detecciones=_detecciones({"Nike": list(range(8)), "Puma": [9]}),
    ),
    "empate_y_coincidencias": dict(
        duracion_s=12.0, intervalo_s=1.0, umbral=0.775, fotogramas_analizados=12,
        detecciones=_detecciones({"Adidas": [0, 1, 2, 3], "Coca-Cola": [0, 1, 2, 3]}),
    ),
    "reparto_igualado": dict(
        duracion_s=20.0, intervalo_s=0.5, umbral=0.5, fotogramas_analizados=40,
        detecciones=_detecciones({"Toyota": list(range(0, 11)), "NFL": list(range(20, 30))}, intervalo=0.5),
    ),
    "una_sola_marca_un_segundo": dict(
        duracion_s=10.0, intervalo_s=1.0, umbral=0.775, fotogramas_analizados=10,
        detecciones=_detecciones({"Apple Inc-": [4]}),
    ),
    "fiabilidad_de_varias_marcas": dict(
        duracion_s=9.0, intervalo_s=1.0, umbral=0.3, fotogramas_analizados=9,
        detecciones=[(0.0, "Chanel", 0.6), (1.0, "Chanel", 0.62), (2.0, "Emirates", 0.7), (5.0, "Pepsi", 0.95)],
    ),
    "una_marca_con_todos_los_hallazgos": dict(
        duracion_s=10.0, intervalo_s=1.0, umbral=0.775, fotogramas_analizados=10,
        detecciones=_detecciones({"Nike": [0, 1, 2, 3, 7, 8]}, confianza=0.7),
    ),
    "sin_detecciones": dict(
        duracion_s=10.0, intervalo_s=1.0, umbral=0.775, fotogramas_analizados=10, detecciones=[],
    ),
    "en_vivo_con_huecos": _en_vivo(
        20.0, [0.0, 2.0, 4.0, 15.0, 4.0, 1.3],
        [(0.0, "Nike", 0.9), (4.0, "Nike", 0.85), (4.0, "Puma", 0.7), (1.3, "Puma", 0.75)],
    ),
    "en_vivo_sin_detecciones": _en_vivo(30.0, [0.0, 0.8, 1.7], []),
}


def _numeros_del_texto(informe: dict) -> list[float]:
    texto = informe["resumen"].replace(NOTA_FINAL, "")
    for marca in informe["marcas"]:
        texto = texto.replace(marca["marca"], "")
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:,\d+)?", texto)]


def _valores(datos) -> set[float]:
    if isinstance(datos, dict):
        return set().union(*(_valores(v) for v in datos.values())) if datos else set()
    if isinstance(datos, list):
        return set().union(*(_valores(v) for v in datos)) if datos else set()
    if isinstance(datos, (int, float)) and not isinstance(datos, bool):
        return {float(datos)}
    return set()


@pytest.mark.parametrize("caso", CASOS)
def test_cada_numero_del_resumen_coincide_con_un_hallazgo(caso):
    informe = construir_informe(**CASOS[caso])
    permitidos = _valores([h["datos"] for h in informe["hallazgos"]])
    numeros = _numeros_del_texto(informe)
    assert numeros, "el resumen debería incluir cifras"
    for numero in numeros:
        assert numero in permitidos, f"{numero} no está en los hallazgos de {caso}"


@pytest.mark.parametrize("caso", CASOS)
def test_mismo_texto_con_los_mismos_datos(caso):
    primero = construir_informe(**CASOS[caso])
    desordenado = dict(CASOS[caso])
    for campo in ("detecciones", "fotogramas"):
        if desordenado.get(campo) is not None:
            desordenado[campo] = list(desordenado[campo])
            random.Random(7).shuffle(desordenado[campo])
    assert construir_informe(**desordenado) == primero


@pytest.mark.parametrize("caso", CASOS)
def test_la_nota_de_limitaciones_aparece_siempre(caso):
    assert construir_informe(**CASOS[caso])["resumen"].endswith(NOTA_FINAL)


def test_sin_detecciones_da_un_texto_coherente():
    informe = construir_informe(**CASOS["sin_detecciones"])
    assert informe["marcas"] == []
    assert informe["hallazgos"] == [{"tipo": "sin_detecciones", "datos": {"fotogramas_analizados": 10, "umbral_pct": 77.5}}]
    assert informe["resumen"].startswith(
        "No se ha detectado ninguna marca en los 10 fotogramas analizados, con un umbral de confianza del 77,5 %.")
    un_fotograma = construir_informe(**{**CASOS["sin_detecciones"], "duracion_s": 0.5, "fotogramas_analizados": 1})
    assert "en el único fotograma analizado" in un_fotograma["resumen"]


def test_varias_cajas_en_un_fotograma_suman_una_sola_vez():
    detecciones = [(0.0, "Nike", 0.9)] * 3 + [(1.0, "Nike", 0.9)]
    informe = construir_informe(10.0, 1.0, 0.775, 10, detecciones)
    assert informe["marcas"][0]["segundos"] == 2.0
    assert informe["marcas"][0]["detecciones"] == 4
    assert informe["marcas"][0]["porcentaje"] == 20.0


def test_texto_completo_de_un_caso_tipico():
    informe = construir_informe(**CASOS["dominante_concentracion_momento"])
    # La racha de Nike son sus 8 segundos, los mismos del titular, así que no se cuenta
    assert informe["resumen"] == (
        "Nike domina el vídeo: acapara la mayor parte del tiempo de marcas, el 88,9 %, con 8 segundos en pantalla. "
        "Su logo tiene más del doble de tiempo en pantalla que el de Puma, la segunda marca: 8 veces el suyo. "
        "Puma aparece una sola vez, en el último tercio del vídeo. "
        + NOTA_FINAL
    )
    assert [h["tipo"] for h in informe["hallazgos"]] == ["marca_dominante", "concentracion", "momento"]
    assert [m["marca"] for m in informe["marcas"]] == ["Nike", "Puma"]


def test_concordancia_y_coma_decimal():
    una = construir_informe(**CASOS["una_sola_marca_un_segundo"])["resumen"]
    assert una.startswith("Apple Inc- es la única marca detectada y aparece durante 1 segundo, el 10 % del vídeo.")
    igualado = construir_informe(**CASOS["reparto_igualado"])["resumen"]
    assert "La marca solo aventaja a NFL en 0,5 segundos" in igualado
    assert "el 52,4 %, con 5,5 segundos en pantalla" in igualado
    assert not re.search(r"\d\.\d", igualado.replace(NOTA_FINAL, ""))


def test_frases_elegidas_segun_los_numeros():
    empate = construir_informe(**CASOS["empate_y_coincidencias"])["resumen"]
    assert empate.startswith("Ninguna marca acapara la mayor parte del tiempo de marcas: Adidas llega al 50 %")
    assert "La marca empata en tiempo en pantalla con Coca-Cola, con 4 segundos cada una." in empate
    assert "Adidas y Coca-Cola aparecen juntas en 4 fotogramas analizados." in empate
    doble = construir_informe(**CASOS["fiabilidad_de_varias_marcas"])["resumen"]
    assert "Su logo dobla en tiempo en pantalla al de Emirates, la segunda marca." in doble
    assert "Todas las apariciones de Chanel están en el primer tercio del vídeo." in doble


def test_la_advertencia_va_al_final():
    informe = construir_informe(**CASOS["fiabilidad_de_varias_marcas"])
    assert informe["hallazgos"][-1]["tipo"] == "fiabilidad"
    assert _resumen_sin_nota(informe).endswith(
        "Atención: Chanel, con un 61 %, y Emirates, con un 70 %, tienen una confianza media por debajo "
        "del 80 %, así que conviene revisar sus detecciones.")


def test_la_advertencia_de_fiabilidad_empieza_por_debajo_del_80():
    for confianza, advierte in ((0.84, False), (0.8, False), (0.79, True)):
        informe = construir_informe(10.0, 1.0, 0.5, 10, _detecciones({"Nike": [0, 4, 8]}, confianza=confianza))
        assert ("fiabilidad" in [h["tipo"] for h in informe["hallazgos"]]) is advierte, confianza
    assert "por debajo del 80 %" in informe["resumen"]
    assert informe["hallazgos"][-1]["datos"] == {"marcas": [{"marca": "Nike", "confianza_pct": 79}], "umbral_pct": 80}


def test_como_maximo_4_hallazgos_y_el_titular_siempre():
    detecciones = _detecciones({"Nike": [*range(10), 20]}, confianza=0.7) + _detecciones({"Puma": [0, 1, 2]})
    informe = construir_informe(30.0, 1.0, 0.5, 30, detecciones)
    # Cumplen su condición 5 hallazgos además del titular, pero solo entran los 3 de más puntuación
    assert [h["tipo"] for h in informe["hallazgos"]] == [
        "marca_dominante", "concentracion", "momento", "aparicion_mas_larga"]


def test_los_segundos_no_superan_la_duracion_del_video():
    informe = construir_informe(10.5, 1.0, 0.775, 11, _detecciones({"Nike": list(range(11))}))
    assert informe["marcas"][0]["segundos"] == 10.5
    assert informe["marcas"][0]["porcentaje"] == 100.0
    # Nike sale en todos los fotogramas: su racha es todo su tiempo y repetiría el titular
    assert [h["tipo"] for h in informe["hallazgos"]] == ["marca_dominante"]
    assert _resumen_sin_nota(informe) == "Nike es la única marca detectada y aparece durante 10,5 segundos, el 100 % del vídeo."


def test_la_racha_de_otra_marca_se_cuenta_aunque_sea_todo_su_tiempo():
    informe = construir_informe(20.0, 1.0, 0.775, 20, _detecciones({"Nike": [0, 2, 4, 6, 8, 10], "Puma": [12, 13, 14, 15]}))
    assert _resumen_sin_nota(informe) == (
        "Nike domina el vídeo: acapara la mayor parte del tiempo de marcas, el 60 %, con 6 segundos en pantalla. "
        "La marca concentra el 66,7 % de su tiempo en pantalla en el primer tercio del vídeo. "
        "La aparición seguida más larga es de Puma: 4 segundos sin salir de pantalla, desde el segundo 12."
    )


def test_frases_seguidas_de_la_misma_marca_no_repiten_el_nombre():
    informe = construir_informe(**CASOS["una_marca_con_todos_los_hallazgos"])
    assert _resumen_sin_nota(informe) == (
        "Nike es la única marca detectada y aparece durante 6 segundos, el 60 % del vídeo. "
        "La marca concentra el 66,7 % de su tiempo en pantalla en el primer tercio del vídeo. "
        "Su logo tiene la aparición seguida más larga: 4 segundos sin salir de pantalla, desde el segundo 0. "
        "Atención: la confianza media de la marca es del 70 %, por debajo del 80 %, así que conviene revisar sus detecciones."
    )
    apple = construir_informe(**CASOS["una_sola_marca_un_segundo"])
    assert _resumen_sin_nota(apple).endswith("Su logo aparece una sola vez, en el tercio central del vídeo.")


def test_tras_una_frase_con_dos_marcas_se_repite_el_nombre():
    # La frase de concentración nombra a Nike y a Puma: «la marca» sería ambiguo después
    informe = construir_informe(**CASOS["dominante_concentracion_momento"])
    assert "Puma aparece una sola vez" in informe["resumen"]
    fiabilidad = construir_informe(**CASOS["fiabilidad_de_varias_marcas"])
    assert "Todas las apariciones de Chanel" in fiabilidad["resumen"]


def test_en_vivo_cada_fotograma_cuenta_hasta_el_siguiente():
    informe = construir_informe(**CASOS["en_vivo_con_huecos"])
    # Fotogramas en 0; 1,3; 2; 4 (dos veces) y 15 de un vídeo de 20 s: pesan 1,3; 0,7; 2; 5 y 5 s
    # Nike: 0 y 4, 1,3 + 5. Puma: 1,3 y 4, 0,7 + 5. El fotograma repetido en 4 cuenta una vez
    assert informe["marcas"] == [
        {"marca": "Nike", "segundos": 6.3, "porcentaje": 31.5, "detecciones": 2, "confianza_media": 0.875},
        {"marca": "Puma", "segundos": 5.7, "porcentaje": 28.5, "detecciones": 2, "confianza_media": 0.725},
    ]


def test_en_vivo_ningun_fotograma_cuenta_mas_de_5_segundos():
    informe = construir_informe(**_en_vivo(60.0, [0.0, 30.0], [(0.0, "Nike", 0.9), (30.0, "Nike", 0.9)]))
    assert informe["marcas"][0]["segundos"] == 10.0
    # El último cuenta hasta el final del vídeo, también con el tope
    final = construir_informe(**_en_vivo(60.0, [0.0, 58.5], [(58.5, "Puma", 0.9)]))
    assert final["marcas"][0]["segundos"] == 1.5


def test_en_vivo_los_fotogramas_sin_detecciones_acortan_el_tiempo():
    detecciones = [(0.0, "Nike", 0.9)]
    solo = construir_informe(**_en_vivo(10.0, [0.0], detecciones))
    con_otro = construir_informe(**_en_vivo(10.0, [0.0, 0.5], detecciones))
    assert solo["marcas"][0]["segundos"] == 5.0
    assert con_otro["marcas"][0]["segundos"] == 0.5


def test_en_vivo_la_racha_suma_los_segundos_de_cada_fotograma():
    fotogramas = [0.0, 1.0, 2.0, 6.0, 7.0, 8.0, 20.0]
    detecciones = [(t, "Nike", 0.9) for t in (0.0, 1.0, 2.0, 8.0)] + [(7.0, "Puma", 0.9)]
    informe = construir_informe(**_en_vivo(30.0, fotogramas, detecciones))
    racha = next(h for h in informe["hallazgos"] if h["tipo"] == "aparicion_mas_larga")
    # 0 a 1, 1 a 2 y 2 a 6: tres fotogramas seguidos que suman 6 segundos
    assert racha["datos"] == {"marca": "Nike", "segundos": 6.0, "desde_s": 0.0}
    assert informe["marcas"][0]["segundos"] == 11.0


def test_en_vivo_sin_detecciones_cuenta_los_fotogramas_analizados():
    informe = construir_informe(**CASOS["en_vivo_sin_detecciones"])
    assert informe["hallazgos"] == [{"tipo": "sin_detecciones", "datos": {"fotogramas_analizados": 3, "umbral_pct": 77.5}}]
