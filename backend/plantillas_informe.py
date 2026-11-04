"""Plantillas del texto del informe.

Se pueden cambiar sin tocar la lógica de informe.py. Los campos entre llaves los rellena
informe.py con valores ya redondeados y con coma decimal. Las unidades, como {u_segundos},
llegan ya en singular o en plural según el número al que acompañan.

Las plantillas _MISMA_MARCA se usan cuando la frase anterior solo habla de la misma marca:
dicen «la marca» o «su logo» en lugar de repetir el nombre.
"""

UNIDADES = {
    "segundos": ("segundo", "segundos"),
    "fotogramas": ("fotograma", "fotogramas"),
}

TERCIOS = {
    "inicio": "el primer tercio del vídeo",
    "mitad": "el tercio central del vídeo",
    "final": "el último tercio del vídeo",
}

# Titular: la parte del tiempo total de marcas que tiene la primera
MARCA_DOMINANTE = {
    "unica": "{marca} es la única marca detectada y aparece durante {segundos} {u_segundos}, el {porcentaje} % del vídeo.",
    "mayor_parte": "{marca} domina el vídeo: acapara la mayor parte del tiempo de marcas, el {cuota} %, con {segundos} {u_segundos} en pantalla.",
    "sin_mayoria": "Ninguna marca acapara la mayor parte del tiempo de marcas: {marca} llega al {cuota} %, con {segundos} {u_segundos} en pantalla.",
}

# Cociente entre los segundos de la primera marca y los de la segunda
CONCENTRACION = {
    "doble": "{marca} dobla en tiempo en pantalla a {segunda}, la segunda marca.",
    "mas_del_doble": "{marca} tiene más del doble de tiempo en pantalla que {segunda}, la segunda marca: {cociente} veces el suyo.",
}
CONCENTRACION_MISMA_MARCA = {
    "doble": "Su logo dobla en tiempo en pantalla al de {segunda}, la segunda marca.",
    "mas_del_doble": "Su logo tiene más del doble de tiempo en pantalla que el de {segunda}, la segunda marca: {cociente} veces el suyo.",
}
REPARTO = {
    "empate": "{marca} y {segunda} empatan en tiempo en pantalla, con {segundos} {u_segundos} cada una.",
    "igualado": "El reparto entre las dos primeras marcas está muy igualado: {marca} solo aventaja a {segunda} en {diferencia} {u_diferencia}.",
}
REPARTO_MISMA_MARCA = {
    "empate": "La marca empata en tiempo en pantalla con {segunda}, con {segundos} {u_segundos} cada una.",
    "igualado": "La marca solo aventaja a {segunda} en {diferencia} {u_diferencia}, así que el reparto entre las dos primeras está muy igualado.",
}

# Tercio del vídeo en el que se concentra una marca
MOMENTO = {
    "una_aparicion": "{marca} aparece una sola vez, en {tercio}.",
    "todo": "Todas las apariciones de {marca} están en {tercio}.",
    "mayoria": "{marca} concentra el {parte} % de su tiempo en pantalla en {tercio}.",
}
MOMENTO_MISMA_MARCA = {
    "una_aparicion": "Su logo aparece una sola vez, en {tercio}.",
    "todo": "Todas las apariciones de su logo están en {tercio}.",
    "mayoria": "La marca concentra el {parte} % de su tiempo en pantalla en {tercio}.",
}

# No se cuenta si es de la marca del titular y dura todo su tiempo, porque lo repetiría
APARICION_MAS_LARGA = "La aparición seguida más larga es de {marca}: {segundos} {u_segundos} sin salir de pantalla, desde el segundo {desde}."
APARICION_MAS_LARGA_MISMA_MARCA = "Su logo tiene la aparición seguida más larga: {segundos} {u_segundos} sin salir de pantalla, desde el segundo {desde}."

COINCIDENCIAS = {
    "una_pareja": "{marca_a} y {marca_b} aparecen juntas en {fotogramas} fotogramas analizados.",
    "varias_parejas": "En {fotogramas} fotogramas analizados aparecen dos o más marcas a la vez, sobre todo {marca_a} y {marca_b}, que coinciden en {fotogramas_pareja} {u_fotogramas_pareja}.",
}

# Advertencia: confianza media por debajo del umbral de fiabilidad
FIABILIDAD = {
    "una": "Atención: la confianza media de {marca} es del {confianza} %, por debajo del {umbral} %, así que conviene revisar sus detecciones.",
    "varias": "Atención: {lista} tienen una confianza media por debajo del {umbral} %, así que conviene revisar sus detecciones.",
}
FIABILIDAD_MISMA_MARCA = "Atención: la confianza media de la marca es del {confianza} %, por debajo del {umbral} %, así que conviene revisar sus detecciones."
FIABILIDAD_ELEMENTO = "{marca}, con un {confianza} %"

SIN_DETECCIONES = {
    "uno": "No se ha detectado ninguna marca en el único fotograma analizado, con un umbral de confianza del {umbral} %. Si esperabas alguna, prueba con un umbral más bajo.",
    "varios": "No se ha detectado ninguna marca en los {fotogramas} fotogramas analizados, con un umbral de confianza del {umbral} %. Si esperabas alguna, prueba con un umbral más bajo.",
}

# Cierra siempre el resumen
NOTA_FINAL = (
    "El modelo reconoce 15 marcas y puede asignar a una de ellas un logo que no conoce. "
    "Los tiempos son aproximados, con un margen de un intervalo de análisis por aparición."
)
