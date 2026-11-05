# Informe técnico · Detección de logos en vídeo

**Computer Vision · P7 IA · Factoría F5 · Ari Basconsuelo**

[Volver al README](../README.md)

Este proyecto entrena un detector de objetos para reconocer los logos de 15 marcas y medir cuánto tiempo aparece cada una en un vídeo. El resultado es una aplicación que recibe un vídeo, lo analiza fotograma a fotograma, guarda cada detección con su recorte en una base de datos y devuelve un informe con el tiempo en pantalla y el porcentaje del vídeo que ocupa cada marca.

Este documento es el informe técnico completo del trabajo. Recoge el dataset, el preprocesado, el entrenamiento, la búsqueda de hiperparámetros, las pruebas fuera del dataset y la decisión sobre volver a entrenar, además de la arquitectura de la aplicación.

## Índice

1. [Planteamiento](#planteamiento)
2. [Dataset](#dataset)
3. [Preprocesado y aumento de datos](#preprocesado-y-aumento-de-datos)
4. [Modelo de partida](#modelo-de-partida)
5. [Entrenamiento](#entrenamiento)
6. [Resultados](#resultados)
7. [Pruebas fuera del dataset](#pruebas-fuera-del-dataset)
8. [Reentrenar o no](#reentrenar-o-no)
9. [Arquitectura de la aplicación](#arquitectura-de-la-aplicación)
10. [Cómo ejecutarlo en local](#cómo-ejecutarlo-en-local)
11. [Limitaciones](#limitaciones)
12. [Líneas futuras](#líneas-futuras)
13. [Fuentes](#fuentes)

## Planteamiento

El enunciado plantea una agencia de publicidad que quiere saber cuánto tiempo aparecen en pantalla los logos de las marcas que representa. El sistema tiene que detectar las marcas en un vídeo, calcular su tiempo de aparición y su porcentaje sobre la duración total, y guardar las detecciones en una base de datos. El procesado no necesita ser en tiempo real.

La tarea es de **detección de objetos**. Para cada fotograma el modelo devuelve cajas delimitadoras con una clase (la marca) y una confianza entre 0 y 1. El tiempo en pantalla se obtiene después, sumando el intervalo que representa cada fotograma analizado en el que aparece la marca.

## Dataset

| Campo | Valor |
| --- | --- |
| Origen | [Logo Brand v2](https://universe.roboflow.com/aitesting-9dz7l/logo-brand/dataset/2), Roboflow Universe |
| Copia de trabajo | Fork en el espacio `ari-basconsuelo`, proyecto `logo-brand-wbytq`, versión 1, exportado en formato YOLO26 |
| Imágenes | 9.639 fotografías reales |
| Clases | 15 marcas |
| División | 7.227 train, 1.451 valid y 961 test (75 %, 15 % y 10 %), la que trae el dataset |
| Etiquetado propio | Ninguno |
| Licencia | La página del dataset no indica una licencia |

Las 15 clases son Adidas, Apple Inc-, Chanel, Coca-Cola, Emirates, Hard Rock Cafe, Mercedes-Benz, NFL, Nike, Pepsi, Puma, Starbucks, The North Face, Toyota y Under Armour. El nombre "Apple Inc-" con guion final es el que trae el dataset y se mantuvo para no romper la correspondencia con las etiquetas.

Se descartó otro dataset de Roboflow, LogoDection v9 con 27 marcas, porque tenía unas 70 imágenes originales por marca y casi siempre con el logo de cerca. También se descartó partir de un modelo ya ajustado sobre LogoDet-3K publicado como brandspotter, porque el 28 de octubre de 2026 sus repositorios en Hugging Face y GitHub no eran accesibles y la elección no tenía una base comprobable.

### Distribución de las clases

Cajas etiquetadas en train por marca. El desequilibrio es leve, con 1,8 veces de diferencia entre la marca más frecuente y la menos frecuente.

| Marca | Cajas en train |
| --- | --- |
| Adidas | 873 |
| Nike | 851 |
| NFL | 734 |
| Coca-Cola | 729 |
| Starbucks | 707 |
| Puma | 674 |
| Emirates | 594 |
| Under Armour | 566 |
| Mercedes-Benz | 555 |
| Chanel | 552 |
| The North Face | 546 |
| Toyota | 535 |
| Apple Inc- | 497 |
| Hard Rock Cafe | 491 |
| Pepsi | 483 |

### Revisión visual de las etiquetas

Para entender qué había aprendido el modelo se generó una hoja de recortes por marca, con una muestra al azar de 64 cajas de train recortadas y colocadas en una cuadrícula. La revisión a ojo mostró tres rasgos del dataset que después explican buena parte de los errores.

* **Contexto concentrado.** Las marcas deportivas (Adidas, Nike, Puma, Under Armour, The North Face, NFL y Emirates) aparecen casi siempre sobre ropa. Emirates sale como "Fly Emirates" en camisetas de fútbol y no hay ningún avión. Starbucks aparece sobre todo en vasos y Mercedes-Benz en parrillas de coche.
* **Variantes ausentes.** No hay ningún recorte de Adidas, Apple ni Mercedes-Benz con la palabra sola sin el símbolo, y Nike casi siempre aparece como símbolo sin texto.
* **Ruido en las etiquetas.** En Chanel aparecen al menos tres cajas con un logo que no es de la marca, y en Adidas algunas cajas cortan el texto por la mitad.

Son conclusiones sobre una muestra de 64 cajas por marca, de unas 550 de media, y no se pueden extrapolar con seguridad al conjunto completo.

## Preprocesado y aumento de datos

**En Roboflow**, al exportar la versión, se aplicó orientación automática y redimensionado a 640 × 640 píxeles en modo *stretch*, sin aumentos. Las particiones de validación y test quedaron sin aumentar para que la evaluación fuera limpia.

El modo *stretch* estira la imagen hasta el cuadrado sin conservar la proporción. Un vídeo 16:9 llega al modelo con otra deformación, porque en inferencia la imagen se encaja en 640 × 640 conservando la proporción y rellenando con gris. Es una diferencia entre entrenamiento y uso que queda señalada como limitación.

**Durante el entrenamiento**, los aumentos fueron los que Ultralytics aplica por defecto. Los más relevantes son estos.

| Aumento | Valor | Efecto |
| --- | --- | --- |
| `hsv_h` | 0,015 | Variación del tono |
| `hsv_v` | 0,4 | Variación del brillo |
| `scale` | 0,5 | Cambio de escala |
| `degrees` | 0 | Sin rotación |
| `fliplr` | 0,5 | Volteo horizontal en la mitad de las imágenes |
| `mosaic` | 1,0 | Combina cuatro imágenes en una, desactivado en las últimas 10 épocas (`close_mosaic`) |

El volteo horizontal se discutió, porque un logo con texto volteado no existe en la realidad. Se dejó el valor por defecto después de que la búsqueda de hiperparámetros, que incluía `fliplr` entre 0 y 0,5, no encontrara una mejora con otros valores. Con 12 intentos es un indicio y no una prueba.

## Modelo de partida

Se hizo **ajuste fino** (*fine-tuning*) de un modelo preentrenado, nunca entrenamiento desde cero. El modelo de partida es **YOLO26n** de Ultralytics, preentrenado en COCO, con unos 2,4 millones de parámetros.

Se eligió el tamaño nano por tres motivos.

1. Entrena rápido en una GPU T4 de Colab, lo que permitía repetir pruebas aunque las sesiones se cortaran.
2. En el momento de elegirlo el plan era servir el modelo en la API de Roboflow, que admite pesos de YOLO26 y publica la tarifa más baja para el nano.
3. Servía como línea base. Si se quedaba corto, habría con qué comparar un modelo mayor.

## Entrenamiento

El entrenamiento se hizo en Google Colab con una GPU T4, guardando los resultados en Google Drive. Las sesiones se cortaron dos veces y Drive permitió retomar con `resume=True` desde la última época guardada.

### Prueba de 3 épocas

Antes del entrenamiento completo se lanzó una prueba corta para medir el tiempo y comprobar que todo funcionaba. Cada época tardó alrededor de 1,6 minutos entre entrenamiento y validación. Con `batch=-1`, la función AutoBatch de Ultralytics eligió un lote de 45 imágenes, el que ocupa alrededor del 60 % de la memoria de la T4. Cada época recorre las 7.227 imágenes de train en 161 lotes.

En validación la prueba alcanzó un mAP50 de 0,817 y un mAP50-95 de 0,642, con una subida en cada época (0,481, 0,585 y 0,641), señal de que el modelo tenía margen.

### Línea base de 100 épocas

```python
from ultralytics import YOLO

model = YOLO("yolo26n.pt")
model.train(
    data="Logo-Brand-1/data.yaml",
    epochs=100,
    imgsz=640,
    batch=-1,
    patience=20,
    seed=0,
    project="/content/drive/MyDrive/logo-detection/runs",
    name="base_yolo26n",
)
```

* `YOLO("yolo26n.pt")` carga los pesos preentrenados en COCO.
* `epochs=100` fija un máximo de 100 recorridos completos de train.
* `imgsz=640` es el tamaño de entrada del modelo.
* `batch=-1` deja que AutoBatch elija el tamaño de lote.
* `patience=20` detiene el entrenamiento si el mAP de validación no mejora en 20 épocas seguidas.
* `seed=0` fija el azar para que el resultado sea reproducible.
* `project` y `name` guardan los resultados en Drive.

El resto de hiperparámetros, incluido el optimizador, quedaron en sus valores por defecto. La ruta de `data` y los nombres pueden variar respecto al cuaderno, que está en `notebooks/entrenamiento.ipynb`.

El entrenamiento completó las 100 épocas en unas 2 horas y 40 minutos. Tres observaciones sobre las curvas.

* **El modelo se estabilizó pronto.** Desde la época 55 el mAP50-95 apenas mejoraba, y de la época 82 a la 100 pasó de 0,715 a 0,716.
* **El efecto del mosaico se ve en la época 91.** Al desactivarse, la pérdida de clasificación de train bajó de golpe (de 0,445 a 0,347) porque las imágenes dejan de estar combinadas. La de validación no cambió.
* **Hay una señal leve de sobreajuste.** Desde la época 55 la pérdida de clasificación de validación se estabilizó (mínimo de 0,66, final de 0,69) mientras la de train bajaba de 0,63 a 0,30. No afectó al resultado, porque el mAP50-95 siguió subiendo hasta la época 99 y el rendimiento en test no empeora respecto a validación.

### Búsqueda de hiperparámetros

Con la línea base terminada se probó a mejorarla con el algoritmo genético de Ultralytics (`model.tune`). Cada iteración entrena un modelo corto con una combinación de hiperparámetros, mide su mAP50-95 en validación y muta la mejor combinación encontrada hasta ese momento.

```python
model = YOLO("yolo26n.pt")
model.tune(
    data="Logo-Brand-1/data.yaml",
    epochs=10,
    iterations=16,
    imgsz=640,
    batch=45,
    optimizer="AdamW",
    close_mosaic=2,
    seed=0,
    space={
        "lr0": (1e-5, 1e-2),
        "lrf": (0.01, 0.5),
        "weight_decay": (0.0, 0.001),
        "hsv_h": (0.0, 0.05),
        "hsv_v": (0.0, 0.9),
        "scale": (0.0, 0.9),
        "degrees": (0.0, 15.0),
        "fliplr": (0.0, 0.5),
        "mosaic": (0.0, 1.0),
    },
    plots=False,
    save=False,
    val=False,
)
```

* `epochs=10` e `iterations=16` lanzan 16 entrenamientos cortos de 10 épocas.
* `batch=45` fija el lote que eligió AutoBatch y evita repetir su cálculo.
* `optimizer="AdamW"` hace que se respete `lr0`, que con `optimizer="auto"` Ultralytics ignora.
* `close_mosaic=2` desactiva el mosaico solo en las 2 últimas épocas. Con el valor por defecto de 10 estaría apagado en toda la iteración.
* `space` define los 9 hiperparámetros que se mutan y sus límites, elegidos a mano.

Por tiempo de GPU se completaron 12 de las 16 iteraciones. La mejor fue la primera, que usa los valores por defecto, con un mAP50-95 de 0,671 a las 10 épocas. Ninguna de las otras 11 la superó (de 0,617 a 0,663). Se comprobó el archivo `best_hyperparameters.yaml` y todos sus valores coincidían con los de por defecto, así que no tenía sentido otro entrenamiento de 100 épocas. El modelo final es el `best.pt` de la línea base.

Hay una limitación conocida de este método que conviene declarar. Las búsquedas cortas favorecen las combinaciones que convergen rápido, que no siempre son las mejores para un entrenamiento largo.

## Resultados

| Ejecución | Configuración | Partición | mAP50 | mAP50-95 |
| --- | --- | --- | --- | --- |
| Prueba | 3 épocas, por defecto | valid | 0,817 | 0,642 |
| Línea base | 100 épocas, lote 45, patience 20 | valid | 0,879 | 0,716 |
| Línea base con umbral | Misma, conf 0,25 | valid | 0,869 | 0,709 |
| Búsqueda de hiperparámetros | 12 iteraciones de 10 épocas, AdamW | valid | 0,859 | 0,671 |
| **Evaluación final** | **Línea base, `best.pt` de la época 99** | **test** | **0,891** | **0,730** |

En validación la línea base obtuvo una precisión de 0,807 y un recall de 0,890. El modelo encuentra casi nueve de cada diez logos, pero alrededor de dos de cada diez detecciones sobran.

La diferencia entre el mAP50 (0,879) y el mAP50-95 (0,716) indica que el modelo encuentra bien los logos y ajusta las cajas con menos exactitud. El mAP50 cuenta como acierto una caja que se solapa al menos un 50 % con la real, mientras que el mAP50-95 promedia diez umbrales de solape más exigentes, del 50 % al 95 %.

### Por marca en test

Las marcas más fuertes en mAP50-95 son The North Face (0,832), Starbucks (0,817) y Hard Rock Cafe (0,808). La más débil es Pepsi (0,480), que también era la peor en validación (0,590), aunque en test solo tiene 30 instancias. Coca-Cola (0,626), Chanel (0,664) y Adidas (0,672) quedan por debajo de la media.

### Matriz de confusión

El modelo casi no confunde unas marcas con otras cuando la caja está bien situada. Sobre 1.428 logos de validación hubo 6 confusiones entre marcas sin umbral y 1 con un umbral de 0,25. Sus errores están en separar logo y fondo. Los falsos positivos pasan de unos 5.250 sin umbral a 648 con un umbral de 0,25, a cambio de perder 34 logos reales más.

### Etiquetas incompletas

En una revisión manual de 48 imágenes de validación el modelo hizo 11 detecciones sin etiqueta. Entre 7 y 8 eran logos reales que el dataset no tenía etiquetados, 2 eran errores (una caja duplicada y un cartel de Waffle House tomado por Starbucks) y 1 no pudo determinarse. Esto significa que parte de los falsos positivos medidos son en realidad aciertos, y que las métricas de precisión están algo infravaloradas. La muestra es pequeña para cuantificarlo en el conjunto.

### Umbral de confianza

La curva F1 de validación alcanza su máximo (0,84) con un umbral de confianza de 0,775. Ese valor está sesgado al alza por las etiquetas incompletas, porque en la muestra revisada había logos reales con confianzas entre 0,4 y 0,7.

El umbral se fijó finalmente en **0,775** después de las pruebas en vídeo, porque con 0,25 el informe atribuía segundos a marcas que no aparecían, y para la agencia ese es el error más grave. El umbral no forma parte de los pesos y se puede cambiar en cada consulta.

## Pruebas fuera del dataset

Las métricas de validación y test miden el modelo sobre imágenes del mismo dataset, con las mismas marcas y el mismo tipo de escenas. Para saber cómo se comporta en el uso real se hicieron tres pruebas manuales.

### Vídeo de una avenida comercial

Se analizó un vídeo de unos 66 segundos grabado en una avenida con escaparates, con un umbral de 0,25. El modelo detectó 11 marcas distintas, muchas de ellas inexistentes en el vídeo.

* Pepsi, Puma, Hard Rock Cafe, Adidas, NFL y Apple no superaron 0,67 de confianza máxima. Un umbral de 0,775 las elimina todas.
* Toyota apareció 5 segundos con confianzas de hasta 0,86, cuando en realidad era un **Volkswagen**. Ese error no se corrige con el umbral.

### Imágenes reales descargadas

Se reunieron 37 fotografías de escenas reales (fachadas, coches, máquinas expendedoras, aviones) y se pasaron por el modelo con el script `scripts/analizar_imagenes.py`. El modelo reconoce bien los logos claros en la forma que aprendió. Falla con Adidas solo con texto o solo con las franjas, le cuesta mucho Nike en fachadas de tienda y casi no detecta Emirates en aviones.

### Vídeo de una sola marca

Con la aplicación ya funcionando se analizó un vídeo de 21 segundos con el logo de Starbucks presente todo el tiempo. El modelo lo detectó en los 22 fotogramas analizados, el 100 % del vídeo, con una confianza media de 0,825.

### Diagnóstico

Las tres pruebas y la revisión de las hojas de recortes apuntan a tres causas que se suman.

1. **Conjunto cerrado.** El modelo solo conoce 15 clases y asume que todo logo es una de ellas. Un logo desconocido con forma parecida se asigna a la marca más cercana, como el Volkswagen leído como Toyota. Toyota y Mercedes-Benz son las únicas marcas que el modelo vio sobre coches, lo que hace probable que cualquier emblema metálico en una parrilla acabe asignado a una de las dos.
2. **Variantes ausentes.** El modelo no reconoce formas del logo que no vio al entrenar, como Adidas solo con la palabra.
3. **Diferencia de dominio.** Muchas marcas se aprendieron en un solo tipo de escena, sobre todo ropa deportiva. En fachadas, coches o aviones el modelo se encuentra con imágenes distintas de las de entrenamiento.

## Reentrenar o no

Se valoró un segundo entrenamiento para corregir las tres causas, ampliando el dataset con más contextos y variantes de las 15 marcas.

**Una clase para logos desconocidos.** Se planteó añadir una clase 16, `otro_logo`, con logos de otras marcas, de modo que el modelo pudiera decir "aquí hay un logo que no es de mi lista" y la agencia obtuviera también el tiempo de las marcas de la competencia. Se descartó por el trabajo de preparación que suponía y queda como limitación declarada.

**Fuentes de datos revisadas.**

| Fuente | Qué aporta | Resultado de la revisión |
| --- | --- | --- |
| [FlickrLogos-32](https://universe.roboflow.com/vu-quoc-minh-dang/flickrlogos32) | 2.237 fotografías de Flickr con 32 marcas, licencia MIT | Solo incluye 5 de las 15 marcas (Adidas, Apple, Coca-Cola, Pepsi y Starbucks) |
| [LogoDet-3K](https://github.com/Wangjing1551/LogoDet-3K-Dataset) (Wang et al., 2020) | 158.652 imágenes y 3.000 marcas | Se descargó y se revisó. Contiene 9 de las 15 marcas con entre 25 y 168 cajas cada una, y le faltan Nike, Emirates, Mercedes-Benz, NFL, Puma y Starbucks. Sus imágenes son sobre todo logos sobre fondo plano, anuncios y catálogos, con pocas escenas reales |
| Logo de Nike de Hypercinema (Roboflow Universe) | 3.272 imágenes con las clases Nike y Nike_text | Sin revisar su contexto |

Con lo encontrado, un reentrenamiento habría mejorado como mucho 5 o 6 marcas y ninguna de las dos que más fallan, Nike y Emirates, en contextos reales. Etiquetar un conjunto propio no cabía en el plazo. **Se decidió mantener el modelo de la línea base** y presentar el diagnóstico como resultado, con sus causas medidas y las vías de mejora documentadas.

## Arquitectura de la aplicación

La aplicación tiene tres piezas, cada una en su carpeta del repositorio, y funciona en dos versiones con el mismo código.

| Pieza | Carpeta | Tecnología | Función |
| --- | --- | --- | --- |
| API del modelo | `api/` | FastAPI y ONNX Runtime | Recibe una imagen y devuelve las detecciones de `best.onnx` |
| Backend | `backend/` | FastAPI, SQLAlchemy y Alembic | Recibe el vídeo, extrae fotogramas, llama a la API del modelo, guarda los resultados y genera el informe |
| Front | `front/` | React | Sube el vídeo, muestra el progreso, dibuja las cajas sobre el vídeo y presenta el informe |

| | Versión nube (portfolio) | Versión local (demo) |
| --- | --- | --- |
| Dónde corre | Render, plan gratuito | El portátil |
| Base de datos | Postgres de Render | SQLite |
| Modos | Informe | Informe y en vivo |
| Tiempo por fotograma | De 3 a 4 segundos | Unos 0,16 segundos |

### API del modelo

El modelo se exportó a ONNX y se sirve con ONNX Runtime en CPU. La API redimensiona cada imagen a 640 × 640 conservando la proporción y rellenando con gris, filtra por el umbral de confianza, elimina las cajas duplicadas con supresión de no máximos (NMS) con un umbral de solape de 0,7 por clase y devuelve cada detección con su marca, su confianza y su caja en píxeles de la imagen original.

Está protegida con una clave en la cabecera `X-API-Key`, que se lee de una variable de entorno y se compara en tiempo constante. Rechaza archivos de más de 5 MB o de más de 4096 × 4096 píxeles, y su documentación interactiva se desactiva en producción.

### Backend

Endpoints principales.

| Endpoint | Función |
| --- | --- |
| `GET /salud` | Comprueba que el servicio responde y lo despierta en Render |
| `GET /config` | Modos activos y tiempo medio por fotograma |
| `POST /analisis` | Recibe un vídeo y lanza su análisis en segundo plano |
| `GET /analisis/{id}` | Estado, progreso y tiempo restante |
| `GET /analisis/{id}/informe` | Tiempo por marca, texto redactado y hallazgos |
| `GET /analisis/{id}/detecciones` | Detecciones con su segundo, para dibujar las cajas |
| `GET /recortes/{id}` | Imagen recortada de cada detección |
| `POST /en-vivo/...` | Sesión de análisis mientras se reproduce el vídeo, solo en la versión local |

El análisis toma un fotograma por segundo, lo reduce a 640 píxeles y lo envía a la API del modelo. Cada detección se guarda con su segundo, su marca, su confianza, su caja y un recorte JPEG. El vídeo se borra al terminar el análisis.

**Cálculo del tiempo en pantalla.** Cada fotograma analizado representa un intervalo de vídeo, 1 segundo por defecto. Si una marca aparece en un fotograma suma ese intervalo, aunque tenga varias cajas en él. El porcentaje es el tiempo de la marca dividido por la duración del vídeo. Es una aproximación con un margen de un intervalo por aparición.

**Informe redactado.** El informe incluye un texto breve generado con reglas y plantillas, sin modelo de lenguaje, siguiendo la técnica de generación de lenguaje natural a partir de datos (Reiter y Dale, 2000) que usa el periodismo automatizado (Graefe, 2016). El programa calcula hallazgos (marca dominante, reparto entre marcas, momento del vídeo, aparición más larga, coincidencias y fiabilidad), elige los más relevantes y los redacta con frases que cambian según los números. Cada cifra del texto sale directamente de los datos y el mismo análisis produce siempre el mismo texto. Se cierra siempre con una nota sobre las limitaciones del modelo.

**Seguridad.** Al no tener cuentas de usuario, la protección se basa en límites de uso. El backend acepta vídeos de hasta 100 MB, 2 minutos y 3840 × 2160 píxeles, comprueba el tipo real del archivo por sus primeros bytes, procesa un solo análisis a la vez y limita las peticiones por minuto de cada IP. La clave de la API del modelo nunca llega al navegador, los errores devuelven mensajes genéricos y las consultas a la base de datos pasan siempre por el ORM. Los requisitos se organizaron siguiendo la lista OWASP API Security Top 10 de 2023.

## Cómo ejecutarlo en local

Las instrucciones de instalación y ejecución, con Docker y sin él, están en el [README](../README.md#probarlo).

## Limitaciones

* **Conjunto cerrado.** El modelo puede asignar a una de sus 15 marcas un logo que no conoce. No hay una clase para logos desconocidos.
* **Dominio del dataset.** Muchas marcas se aprendieron sobre ropa deportiva. El rendimiento baja en fachadas, coches, aviones y anuncios.
* **Variantes ausentes.** El modelo no reconoce algunas formas de los logos, como Adidas solo con la palabra.
* **Etiquetas incompletas y con ruido**, que afectan a la medición de la precisión y al aprendizaje.
* **Redimensionado en modo *stretch*** en el entrenamiento, distinto del encaje con proporción que se usa en inferencia.
* **Tiempo aproximado.** Se analiza un fotograma por segundo, así que una aparición más corta puede no contarse.
* **Velocidad en la nube.** En el plan gratuito de Render cada fotograma tarda de 3 a 4 segundos, y un vídeo de 1 minuto unos 3,5 minutos. El servicio se duerme tras 15 minutos sin uso, y su Postgres gratuito caduca a los 30 días.
* **Incorporar una marca exige volver a entrenar.**
* **Licencias.** Los modelos YOLO de Ultralytics se distribuyen con licencia AGPL-3.0. El dataset no indica licencia en su página.

## Líneas futuras

* Ampliar el dataset con escenas reales de las marcas más débiles en uso, sobre todo Nike y Emirates, etiquetando un conjunto propio pequeño.
* Añadir la clase `otro_logo` para medir también el tiempo de otras marcas.
* Probar un modelo mayor, como YOLO26s, y una resolución de entrada mayor para los logos pequeños.
* Explorar arquitecturas en dos etapas, con un detector genérico de logos y una comparación con imágenes de referencia de cada marca, que permiten añadir marcas sin reentrenar (Tüzkö et al., 2018. Fehérvári y Appalaraju, 2019).
* Explorar detectores de vocabulario abierto como YOLO-World (Cheng et al., 2024) o YOLOE, que reciben las clases en el momento de la inferencia. No se han encontrado evaluaciones publicadas sobre logos.

## Fuentes

**Artículos y trabajos académicos**

* Cheng, T., Song, L., Ge, Y., Liu, W., Wang, X. y Shan, Y. (2024). [YOLO-World. Real-Time Open-Vocabulary Object Detection](https://openaccess.thecvf.com/content/CVPR2024/html/Cheng_YOLO-World_Real-Time_Open-Vocabulary_Object_Detection_CVPR_2024_paper.html). CVPR 2024.
* Fehérvári, I. y Appalaraju, S. (2019). [Scalable Logo Recognition Using Proxies](https://mlanthology.org/wacv/2019/fehervari2019wacv-scalable). WACV 2019.
* Graefe, A. (2016). [Guide to Automated Journalism](https://data.journalism.columbia.edu/sites/data.journalism.columbia.edu/files/content/guide-to-automated-journalism.pdf). Tow Center for Digital Journalism, Universidad de Columbia.
* Reiter, E. y Dale, R. (2000). [Building Natural Language Generation Systems](https://www.cambridge.org/core/books/building-natural-language-generation-systems/architecture-of-a-natural-language-generation-system/048E2C49A80D37B3B8BA69DD5FA823F9). Cambridge University Press.
* Tüzkö, A., Herrmann, C., Manger, D. y Beyerer, J. (2018). [Open Set Logo Detection and Retrieval](https://arxiv.org/abs/1710.10891). VISAPP 2018.
* Wang, J., Min, W., Hou, S., Ma, S., Zheng, Y. y Jiang, S. (2020). [LogoDet-3K. A Large-Scale Image Dataset for Logo Detection](https://arxiv.org/abs/2008.05359). arXiv 2008.05359.

**Documentación oficial**

* Ultralytics, [Tips for Best Training Results](https://docs.ultralytics.com/yolov5/tutorials/tips_for_best_training_results).
* Ultralytics, [Hyperparameter Tuning](https://docs.ultralytics.com/guides/hyperparameter-tuning).
* Ultralytics, [YOLOE](https://docs.ultralytics.com/models/yoloe).
* Ultralytics, [YOLO11 vs YOLO26](https://docs.ultralytics.com/compare/yolo11-vs-yolo26).
* Roboflow, [YOLO26](https://docs.roboflow.com/models/supported-models/yolo26.md) y [Roboflow Pricing](https://roboflow.com/pricing).
* Render, [Deploy for Free](https://render.com/docs/free) y [Fully Managed TLS Certificates](https://render.com/docs/tls).

**Datasets**

* [Logo Brand v2](https://universe.roboflow.com/aitesting-9dz7l/logo-brand/dataset/2), Roboflow Universe.
* [FlickrLogos32](https://universe.roboflow.com/vu-quoc-minh-dang/flickrlogos32), Roboflow Universe.
* [LogoDet-3K](https://github.com/Wangjing1551/LogoDet-3K-Dataset), repositorio de los autores.

**Otras**

* APIsecurity.io, [OWASP API Security Top 10](https://apisecurity.io/owasp-api-security-top-10/), fuente secundaria de la lista de OWASP.
