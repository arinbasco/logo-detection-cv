"""Informe por marca y resumen redactado a partir de los datos, sin modelo de lenguaje.

Sigue las tres etapas de la generación de lenguaje natural a partir de datos que describen
Reiter y Dale (2000): qué contar, cómo decirlo y en qué orden. Cada cifra del texto sale de
los hallazgos, y los mismos datos producen siempre el mismo texto.
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations

import plantillas_informe as plantillas

# Reglas de la especificación
HALLAZGOS_MAXIMOS = 4
COCIENTE_CONCENTRACION = 2.0
COCIENTE_REPARTO = 1.2
PARTE_TERCIO_PCT = 60.0
RACHA_MINIMA_S = 3.0
COINCIDENCIAS_MINIMAS = 3
CONFIANZA_FIABLE_PCT = 80  # 0,80 escrito como porcentaje
MAXIMO_POR_FOTOGRAMA_S = 5.0  # modo en vivo: una pausa o un salto no inflan los tiempos
TOLERANCIA = 1e-9

# Posición de cada hallazgo en la tabla: desempata puntuaciones y ordena los detalles
ORDEN = {
    "marca_dominante": 0,
    "concentracion": 1,
    "reparto": 1,
    "momento": 2,
    "aparicion_mas_larga": 3,
    "coincidencias": 4,
    "fiabilidad": 5,
}
TERCIOS = ("inicio", "mitad", "final")


@dataclass
class Hallazgo:
    tipo: str
    datos: dict
    frase: str
    puntuacion: float = math.inf  # el titular entra siempre
    marcas: tuple[str, ...] = ()  # marcas que nombra la frase, la protagonista primero
    frase_misma_marca: str | None = None  # la misma frase sin repetir el nombre de la protagonista


@dataclass
class Marca:
    nombre: str
    muestras: list[int]  # números de los fotogramas analizados en los que aparece
    segundos: float
    porcentaje: float
    cajas: int
    confianza_media: float


@dataclass
class Muestreo:
    """Fotogramas analizados, numerados en orden, con el segundo y el peso de cada uno.

    En el modo informe todos pesan 1 y cada uno representa intervalo_s segundos. En el
    modo en vivo los fotogramas no llegan a intervalos fijos: cada uno pesa los segundos
    que representa y segundos_por_peso es 1.
    """

    instantes: dict[int, float]
    pesos: dict[int, float]
    segundos_por_peso: float
    duracion_s: float

    def peso(self, muestras) -> float:
        return math.fsum(self.pesos[k] for k in muestras)  # mismo resultado en cualquier orden

    def segundos(self, muestras) -> float:
        # El último fotograma puede representar un intervalo que pasa del final del vídeo
        return min(self.peso(muestras) * self.segundos_por_peso, self.duracion_s)


def numero(valor: float, decimales: int = 1) -> str:
    """Número con coma decimal y sin ceros sobrantes, por ejemplo 12 o 12,5."""
    redondeado = round(valor, decimales)
    if redondeado == int(redondeado):
        return str(int(redondeado))
    return f"{redondeado:.{decimales}f}".replace(".", ",")


def unidad(texto_numero: str, clave: str) -> str:
    """Singular solo para 1: 1 segundo, 0,5 segundos, 2 segundos."""
    singular, plural = plantillas.UNIDADES[clave]
    return singular if texto_numero == "1" else plural


def _muestreo_informe(detecciones, duracion_s: float, intervalo_s: float):
    """Modo informe: los fotogramas se analizan cada intervalo_s segundos desde el segundo 0."""
    instantes: dict[int, float] = {}
    numeradas = []
    for t_s, marca, confianza in detecciones:
        k = round(t_s / intervalo_s)
        instantes.setdefault(k, t_s)
        numeradas.append((k, marca, confianza))
    return Muestreo(instantes, dict.fromkeys(instantes, 1.0), intervalo_s, duracion_s), numeradas


def _muestreo_en_vivo(detecciones, duracion_s: float, fotogramas: list[float]):
    """Modo en vivo: cada fotograma cuenta desde su segundo hasta el del siguiente.

    El último cuenta hasta el final del vídeo, y ninguno más de 5 segundos. Los que llegan
    con el mismo segundo cuentan como uno solo.
    """
    # Un fotograma con detecciones es siempre un fotograma analizado
    segundos = sorted(set(fotogramas) | {t_s for t_s, _, _ in detecciones})
    instantes = dict(enumerate(segundos))
    pesos = {
        k: max(0.0, min(fin - inicio, MAXIMO_POR_FOTOGRAMA_S))
        for k, (inicio, fin) in enumerate(zip(segundos, [*segundos[1:], duracion_s]))
    }
    numero_de = {t_s: k for k, t_s in instantes.items()}
    numeradas = [(numero_de[t_s], marca, confianza) for t_s, marca, confianza in detecciones]
    return Muestreo(instantes, pesos, 1.0, duracion_s), numeradas


def _estadisticas(numeradas, muestreo: Muestreo):
    """Agrupa las detecciones por marca y por fotograma analizado.

    Una marca suma el tiempo de un fotograma una sola vez, aunque tenga varias cajas en él.
    """
    muestras: dict[str, set[int]] = defaultdict(set)
    cajas: Counter[str] = Counter()
    confianzas: dict[str, list[float]] = defaultdict(list)
    marcas_por_muestra: dict[int, set[str]] = defaultdict(set)
    for k, marca, confianza in numeradas:
        muestras[marca].add(k)
        cajas[marca] += 1
        confianzas[marca].append(confianza)
        marcas_por_muestra[k].add(marca)

    duracion_s = muestreo.duracion_s
    marcas = []
    for nombre, ks in muestras.items():
        segundos = muestreo.segundos(ks)
        marcas.append(Marca(
            nombre=nombre,
            muestras=sorted(ks),
            segundos=round(segundos, 3),
            porcentaje=round(segundos / duracion_s * 100, 1) if duracion_s > 0 else 0.0,
            cajas=cajas[nombre],
            confianza_media=round(sum(confianzas[nombre]) / len(confianzas[nombre]), 3),
        ))
    marcas.sort(key=lambda m: (-m.segundos, m.nombre))
    return marcas, marcas_por_muestra


def _racha(muestras: list[int], pesos: dict[int, float]) -> tuple[int, int, float]:
    """Comienzo, largo y peso de la racha de fotogramas seguidos que más pesa; la primera si empatan."""
    mejor_inicio, mejor_largo, mejor_peso = 0, 0, -1.0
    inicio = anterior = None
    peso = 0.0
    for k in muestras:
        if anterior is None or k != anterior + 1:
            inicio, peso = k, 0.0
        peso += pesos[k]
        anterior = k
        if peso > mejor_peso:
            mejor_inicio, mejor_largo, mejor_peso = inicio, k - inicio + 1, peso
    return mejor_inicio, mejor_largo, mejor_peso


# Paso 1, qué contar: cada función calcula un hallazgo y su puntuación, o None si no se cumple
# su condición. La puntuación mide cuánto se aleja el valor de su umbral. Paso 2, cómo
# decirlo: cada hallazgo trae su frase y, si nombra a una marca protagonista, otra versión
# para cuando la frase anterior ya hablaba solo de ella.

def _marca_dominante(marcas: list[Marca]) -> Hallazgo:
    primera = marcas[0]
    total = sum(m.segundos for m in marcas)
    cuota = round(primera.segundos / total * 100, 1) if total > 0 else 0.0
    segundos = round(primera.segundos, 1)
    datos = {"marca": primera.nombre, "segundos": segundos, "porcentaje_video": primera.porcentaje, "cuota_pct": cuota}
    if len(marcas) == 1:
        variante = "unica"
    elif cuota > 50:
        variante = "mayor_parte"
    else:
        variante = "sin_mayoria"
    frase = plantillas.MARCA_DOMINANTE[variante].format(
        marca=primera.nombre, segundos=numero(segundos), u_segundos=unidad(numero(segundos), "segundos"),
        porcentaje=numero(primera.porcentaje), cuota=numero(cuota),
    )
    return Hallazgo("marca_dominante", datos, frase, marcas=(primera.nombre,))


def _concentracion_o_reparto(marcas: list[Marca]) -> Hallazgo | None:
    if len(marcas) < 2 or marcas[1].segundos <= 0:
        return None  # sin una segunda marca con tiempo en pantalla no hay cociente
    primera, segunda = marcas[0], marcas[1]
    cociente = primera.segundos / segunda.segundos
    datos = {
        "marca": primera.nombre, "segunda": segunda.nombre, "segundos": round(primera.segundos, 1),
        "segundos_segunda": round(segunda.segundos, 1), "cociente": round(cociente, 1),
    }
    nombradas = (primera.nombre, segunda.nombre)
    if cociente >= COCIENTE_CONCENTRACION - TOLERANCIA:
        variante = "doble" if datos["cociente"] == COCIENTE_CONCENTRACION else "mas_del_doble"
        campos = dict(marca=primera.nombre, segunda=segunda.nombre, cociente=numero(datos["cociente"]))
        return Hallazgo(
            "concentracion", datos, plantillas.CONCENTRACION[variante].format(**campos),
            cociente / COCIENTE_CONCENTRACION, nombradas,
            plantillas.CONCENTRACION_MISMA_MARCA[variante].format(**campos),
        )
    if cociente < COCIENTE_REPARTO:
        diferencia = round(primera.segundos - segunda.segundos, 1)
        datos["diferencia_s"] = diferencia
        variante = "empate" if diferencia == 0 else "igualado"
        campos = dict(
            marca=primera.nombre, segunda=segunda.nombre,
            segundos=numero(datos["segundos"]), u_segundos=unidad(numero(datos["segundos"]), "segundos"),
            diferencia=numero(diferencia), u_diferencia=unidad(numero(diferencia), "segundos"),
        )
        return Hallazgo(
            "reparto", datos, plantillas.REPARTO[variante].format(**campos), COCIENTE_REPARTO / cociente,
            nombradas, plantillas.REPARTO_MISMA_MARCA[variante].format(**campos),
        )
    return None


def _momento(marcas: list[Marca], muestreo: Muestreo) -> Hallazgo | None:
    """La marca más concentrada en un tercio del vídeo, si pasa del 60 % de su tiempo."""
    duracion_s = muestreo.duracion_s
    mejor = None
    for m in marcas:  # en caso de empate gana la de más segundos, que va antes
        por_tercio = [0.0, 0.0, 0.0]
        for k in m.muestras:
            tercio = min(2, int(3 * muestreo.instantes[k] / duracion_s)) if duracion_s > 0 else 0
            por_tercio[tercio] += muestreo.pesos[k]
        total = sum(por_tercio)
        if total <= 0:
            continue
        parte = round(max(por_tercio) / total * 100, 1)
        if parte > PARTE_TERCIO_PCT and (mejor is None or parte > mejor[0]):
            mejor = (parte, m, TERCIOS[por_tercio.index(max(por_tercio))])
    if mejor is None:
        return None
    parte, m, tercio = mejor
    if len(m.muestras) == 1:
        variante = "una_aparicion"
    elif parte == 100:
        variante = "todo"
    else:
        variante = "mayoria"
    campos = dict(marca=m.nombre, parte=numero(parte), tercio=plantillas.TERCIOS[tercio])
    return Hallazgo(
        "momento", {"marca": m.nombre, "tercio": tercio, "parte_pct": parte},
        plantillas.MOMENTO[variante].format(**campos), parte / PARTE_TERCIO_PCT, (m.nombre,),
        plantillas.MOMENTO_MISMA_MARCA[variante].format(**campos),
    )


def _aparicion_mas_larga(marcas: list[Marca], muestreo: Muestreo) -> Hallazgo | None:
    """La racha más larga de fotogramas seguidos con la misma marca, si dura 3 segundos o más."""
    inicio, largo, _, marca = max(
        ((*_racha(m.muestras, muestreo.pesos), m) for m in marcas), key=lambda r: r[2]
    )  # max devuelve la primera en caso de empate, la de más segundos
    segundos = muestreo.segundos(range(inicio, inicio + largo))
    if segundos < RACHA_MINIMA_S - TOLERANCIA:
        return None
    # Si la racha es todo el tiempo de la marca del titular, repetiría lo que dice el titular
    if marca is marcas[0] and abs(segundos - muestreo.segundos(marca.muestras)) <= TOLERANCIA:
        return None
    datos = {"marca": marca.nombre, "segundos": round(segundos, 1), "desde_s": round(muestreo.instantes[inicio], 1)}
    campos = dict(
        marca=marca.nombre, segundos=numero(datos["segundos"]),
        u_segundos=unidad(numero(datos["segundos"]), "segundos"), desde=numero(datos["desde_s"]),
    )
    return Hallazgo(
        "aparicion_mas_larga", datos, plantillas.APARICION_MAS_LARGA.format(**campos),
        segundos / RACHA_MINIMA_S, (marca.nombre,), plantillas.APARICION_MAS_LARGA_MISMA_MARCA.format(**campos),
    )


def _coincidencias(marcas_por_muestra: dict[int, set[str]]) -> Hallazgo | None:
    """Fotogramas analizados con dos o más marcas a la vez, si son 3 o más."""
    con_varias = [sorted(marcas) for _, marcas in sorted(marcas_por_muestra.items()) if len(marcas) >= 2]
    if len(con_varias) < COINCIDENCIAS_MINIMAS:
        return None
    parejas = Counter(pareja for marcas in con_varias for pareja in combinations(marcas, 2))
    (marca_a, marca_b), veces = min(parejas.items(), key=lambda p: (-p[1], p[0]))
    datos = {"fotogramas": len(con_varias), "marca_a": marca_a, "marca_b": marca_b, "fotogramas_pareja": veces}
    frase = plantillas.COINCIDENCIAS["una_pareja" if veces == len(con_varias) else "varias_parejas"].format(
        marca_a=marca_a, marca_b=marca_b, fotogramas=len(con_varias), fotogramas_pareja=veces,
        u_fotogramas_pareja=unidad(numero(veces), "fotogramas"),
    )
    return Hallazgo("coincidencias", datos, frase, len(con_varias) / COINCIDENCIAS_MINIMAS, (marca_a, marca_b))


def _fiabilidad(marcas: list[Marca]) -> Hallazgo | None:
    """Advertencia para las marcas con confianza media por debajo del 80 %."""
    bajas = [(m.nombre, round(m.confianza_media * 100)) for m in marcas]
    bajas = [(nombre, confianza) for nombre, confianza in bajas if confianza < CONFIANZA_FIABLE_PCT]
    if not bajas:
        return None
    datos = {
        "marcas": [{"marca": nombre, "confianza_pct": confianza} for nombre, confianza in bajas],
        "umbral_pct": CONFIANZA_FIABLE_PCT,
    }
    peor = max(min(confianza for _, confianza in bajas), 1)
    puntuacion = CONFIANZA_FIABLE_PCT / peor
    nombradas = tuple(nombre for nombre, _ in bajas)
    if len(bajas) == 1:
        campos = dict(marca=bajas[0][0], confianza=bajas[0][1], umbral=CONFIANZA_FIABLE_PCT)
        return Hallazgo(
            "fiabilidad", datos, plantillas.FIABILIDAD["una"].format(**campos), puntuacion, nombradas,
            plantillas.FIABILIDAD_MISMA_MARCA.format(**campos),
        )
    elementos = [plantillas.FIABILIDAD_ELEMENTO.format(marca=n, confianza=c) for n, c in bajas]
    lista = ", ".join(elementos[:-1]) + ", y " + elementos[-1] + ","
    frase = plantillas.FIABILIDAD["varias"].format(lista=lista, umbral=CONFIANZA_FIABLE_PCT)
    return Hallazgo("fiabilidad", datos, frase, puntuacion, nombradas)


def _sin_detecciones(fotogramas_analizados: int, umbral: float) -> Hallazgo:
    umbral_pct = round(umbral * 100, 1)
    frase = plantillas.SIN_DETECCIONES["uno" if fotogramas_analizados == 1 else "varios"].format(
        fotogramas=fotogramas_analizados, umbral=numero(umbral_pct))
    return Hallazgo("sin_detecciones", {"fotogramas_analizados": fotogramas_analizados, "umbral_pct": umbral_pct}, frase)


def _redactar(elegidos: list[Hallazgo]) -> list[str]:
    """Frases en orden. Si la anterior solo nombra a la misma marca, no se repite su nombre.

    Si la anterior nombra a dos marcas, se repite, porque «la marca» sería ambiguo.
    """
    frases = [elegidos[0].frase]
    for anterior, hallazgo in zip(elegidos, elegidos[1:]):
        misma_marca = hallazgo.frase_misma_marca is not None and anterior.marcas == hallazgo.marcas[:1]
        frases.append(hallazgo.frase_misma_marca if misma_marca else hallazgo.frase)
    return frases


def construir_informe(
    duracion_s: float,
    intervalo_s: float | None,
    umbral: float,
    fotogramas_analizados: int,
    detecciones: list[tuple[float, str, float]],
    fotogramas: list[float] | None = None,
) -> dict:
    """Informe completo: tabla por marca, resumen redactado y hallazgos que lo justifican.

    detecciones es una lista de (segundo, marca, confianza), una por caja. En el modo en
    vivo, fotogramas trae el segundo de cada fotograma analizado, tenga detecciones o no,
    e intervalo_s no se usa.
    """
    # Mismo orden siempre, venga como venga de la base de datos, para que el texto no cambie
    detecciones = sorted(detecciones)
    if fotogramas is None:
        muestreo, numeradas = _muestreo_informe(detecciones, duracion_s, intervalo_s)
    else:
        muestreo, numeradas = _muestreo_en_vivo(detecciones, duracion_s, fotogramas)
    marcas, marcas_por_muestra = _estadisticas(numeradas, muestreo)

    if not marcas:
        elegidos = [_sin_detecciones(fotogramas_analizados, umbral)]
    else:
        candidatos = [
            hallazgo
            for hallazgo in (
                _concentracion_o_reparto(marcas),
                _momento(marcas, muestreo),
                _aparicion_mas_larga(marcas, muestreo),
                _coincidencias(marcas_por_muestra),
                _fiabilidad(marcas),
            )
            if hallazgo is not None
        ]
        # El titular ocupa uno de los 4 huecos; el resto, por puntuación y orden de la tabla
        candidatos.sort(key=lambda h: (-h.puntuacion, ORDEN[h.tipo]))
        elegidos_extra = candidatos[:HALLAZGOS_MAXIMOS - 1]
        # Paso 3, orden: titular, detalles en el orden de la tabla y al final las advertencias
        detalles = sorted((h for h in elegidos_extra if h.tipo != "fiabilidad"), key=lambda h: ORDEN[h.tipo])
        advertencias = [h for h in elegidos_extra if h.tipo == "fiabilidad"]
        elegidos = [_marca_dominante(marcas), *detalles, *advertencias]

    resumen = " ".join([*_redactar(elegidos), plantillas.NOTA_FINAL])
    return {
        "marcas": [
            {
                "marca": m.nombre,
                "segundos": m.segundos,
                "porcentaje": m.porcentaje,
                "detecciones": m.cajas,
                "confianza_media": m.confianza_media,
            }
            for m in marcas
        ],
        "resumen": resumen,
        "hallazgos": [{"tipo": h.tipo, "datos": h.datos} for h in elegidos],
    }
