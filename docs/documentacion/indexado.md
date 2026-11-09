# Indexado y evaluación

## Indexar

Indexar convierte las fuentes de una KB en fragmentos con su vector, para que DeepTutor las
encuentre por significado. Necesita `[ollama]` en `atril.toml` y Ollama con el modelo de
embedding descargado (atril comprueba ambas cosas antes de empezar).

`atril kb indexar <temario> [kb]` (o **Indexar** en Temarios):

1. Vuelve a aplicar `[indexado]` a DeepTutor (lector de PDF, tamaño de fragmento, ritmo).
2. Compara cada fuente con `fuentes\indexado.json` y añade **solo las nuevas**, una a una, con
   la línea de comandos de DeepTutor (no hace falta tenerlo arrancado).
3. Anota en `indexado.json` la huella (SHA-256) de cada fuente indexada.

El proceso de DeepTutor corre con **prioridad baja** de CPU y disco, y con `[indexado] hilos`
como límite de hilos, para que el ordenador siga respondiendo.

!!! tip "Se puede interrumpir"
    Cancelar (o cerrar la ventana, o pulsar ++ctrl+c++) para en un punto seguro. Al repetir
    el comando continúa por la fuente pendiente, y DeepTutor reutiliza el lector en caché.

### Estados de una fuente

| Estado | Significa | Qué hacer |
|---|---|---|
| Indexada | La versión del disco es la indexada. | Nada. |
| Por indexar | Es nueva. | **Indexar**. |
| Cambiada: reindexar | El fichero ha cambiado desde que se indexó. | **Reindexar**. |
| Sin fichero | Está declarada pero no en disco. | **Descargar** (si tiene URL) o colocarla a mano. |
| Retirada: reindexar | Se indexó, pero ya no está en el temario. | **Reindexar**. |

## Reindexar

DeepTutor no borra vectores al quitar un documento y guarda una versión nueva con el mismo
nombre como `nombre (2).pdf`. Por eso las fuentes cambiadas o retiradas solo se resuelven con
`atril kb reindexar <kb>` (o **Reindexar**):

1. Arranca DeepTutor si hace falta (usa su API).
2. Quita de la KB las versiones anteriores y las fuentes retiradas.
3. Añade las versiones nuevas.
4. Rehace fragmentos y vectores con el modelo de embedding activo, reutilizando el lector en
   caché, y espera a que DeepTutor termine (puede tardar bastante: es trabajo de la GPU).
5. Si arrancó DeepTutor solo para esto, lo para al terminar.

Si se interrumpe, repetirlo continúa donde se quedó.

!!! warning "Indexados interrumpidos"
    Si un indexado de DeepTutor quedó a medias (el proceso murió), atril lo marca como
    *interrumpido* y pide **reiniciar DeepTutor** antes de reindexar.

## Ritmo y rendimiento

Cuatro claves de `[indexado]` cambian el ritmo, no el resultado:

| Clave | Efecto | Si el equipo se resiente |
|---|---|---|
| `hilos` | Hilos de CPU del lector y el troceado (`0` = sin límite). | Bájalo, por ejemplo a la mitad de los núcleos. |
| `lote_embedding` | Fragmentos por petición al modelo. | Bájalo: ráfagas de GPU más cortas. |
| `pausa_embedding` | Milisegundos mínimos entre peticiones. | Súbelo: deja huecos libres a la GPU. |
| `descargar_modelos` | Deja que Docling o MinerU descarguen sus modelos. | — |

!!! note "Memoria de vídeo"
    Si el modelo de embedding no cabe entero en la memoria de la tarjeta, la parte que no cabe
    va a la CPU y la satura. `atril estado` avisa de ello y de otros modelos cargados en Ollama.

## Evaluar

`atril kb evaluar <kb>` mide si la búsqueda encuentra lo que debe. Usa un conjunto de
preguntas con sus respuestas de referencia, en el formato JSONL del evaluador de DeepTutor
(por defecto, el fichero de `evaluacion` de la KB, por ejemplo `eval/cte-v2.jsonl`).

Para cada pregunta, atril busca en la KB y comprueba si la respuesta aparece en alguno de los
`k` primeros fragmentos (`-k 5` por defecto), comparando con el **texto completo** de cada
fragmento (la evaluación de DeepTutor solo mira los 200 primeros caracteres).

El informe se guarda en `temarios\<t>\eval\informes\` y se compara con el anterior de la misma
KB, conjunto de preguntas y `k`, para ver si un cambio de parser o de fragmento mejora o
empeora. Los informes nunca van dentro de `espacio\`, que el tutor lee.
