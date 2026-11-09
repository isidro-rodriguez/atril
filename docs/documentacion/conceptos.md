# Conceptos

Las piezas con las que trabaja atril y dónde vive cada una.

## Estación

La **estación** es la carpeta donde viven DeepTutor, tus temarios y sus datos. Hay **una por
ordenador**: atril la guarda en la variable de usuario `ATRIL_ESTACION` (en Windows, en el
registro del usuario) y la usa desde cualquier carpeta. La primera ejecución la elige o la
crea con un `atril.toml` mínimo.

Su estructura es fija:

| Ruta | Contenido | En las copias |
|---|---|---|
| `atril.toml` | Configuración de la estación ([referencia](atril-toml.md)) | Sí |
| `app\` | DeepTutor: su código, su entorno de Python y su web | No (se reinstala) |
| `data\` | Datos de DeepTutor (`DEEPTUTOR_HOME`): ajustes, bases de conocimiento, índices, chats | Sí |
| `data\atril\` | Datos de la ventana: actividad, temario activo, Ollama abierto por atril | Sí (sin `logs\`) |
| `temarios\<id>\` | Un temario: `temario.toml`, `prompt.md`, fuentes, histórico y evaluación | Sí |
| `.atril.lock` | Bloqueo mientras dura una operación larga | No |

!!! note "El código de atril nunca está en la estación"
    Atril se instala aparte (con el instalador o con `uv tool`). Así se puede reinstalar o
    actualizar sin tocar tus datos, y la estación se puede copiar entera a otro disco.

Mientras dura una operación larga (backup, restauración, instalación, actualización,
indexado), atril bloquea `.atril.lock`: otra no puede empezar hasta que termine. Si el proceso
muere, el sistema libera el bloqueo solo.

## Temario

Una asignatura, una oposición o cualquier conjunto de documentos que quieras estudiar junto.
Cada temario es una carpeta `temarios\<id>\` con:

| Fichero o carpeta | Contenido |
|---|---|
| `temario.toml` | Nombre, bases de conocimiento y fuentes ([referencia](temario-toml.md)) |
| `prompt.md` | Instrucciones para el tutor (tono, cómo citar, qué buscar en web) |
| `fuentes\<carpeta>\` | Los PDF vigentes, con nombre estable |
| `fuentes\historico\` | Versiones anteriores de las fuentes descargadas |
| `fuentes\registro.json` | Huella, tamaño y fechas de cada fuente descargada |
| `fuentes\indexado.json` | Qué versión de cada fuente está indexada en cada KB |
| `eval\` | Preguntas de evaluación e informes |

## Base de conocimiento (KB)

Lo que DeepTutor consulta para responder: tus fuentes troceadas en fragmentos y convertidas en
vectores (*embeddings*) para buscarlas por significado. Un temario puede tener varias; por
ejemplo, una con la norma (vinculante) y otra con guías y apuntes. El id de cada KB es único en
toda la estación, porque DeepTutor las guarda todas juntas.

Crear los vectores es **indexar** ([detalles](indexado.md)). Necesita
[Ollama](https://ollama.com/) con un modelo de embedding; sin Ollama, DeepTutor funciona, pero
no puede buscar en tus documentos.

## Fuente

Cada documento de un temario: un PDF tuyo (manual), un PDF de internet que atril descarga y
vigila, una carpeta de Markdown o, de forma experimental, un repositorio de GitHub o una web.
Cada fuente pertenece a **exactamente una** KB.

## DeepTutor

[DeepTutor](https://github.com/HKUDS/DeepTutor) es el tutor: un servidor (puerto `8001`) y una
web (puerto `3782`) que atril instala en `app\`. Atril nunca lo importa: lo maneja con su
línea de comandos y su API.

### Parches

Pequeñas correcciones de atril sobre el código de DeepTutor, que se eligen en
`[deeptutor] parches`:

| Parche | Qué corrige |
|---|---|
| `paginas-citas` | Las citas muestran la página aunque el PDF no tenga etiquetas de página. |
| `arranque-sin-ventana` | En Windows, arrancar DeepTutor no abre una consola vacía. |

Un parche solo se aplica si el código original está intacto. Si DeepTutor cambia ese código,
atril lo dice y no fuerza nada. Al arrancar, atril aplica los parches pendientes.

## Ollama

Ollama vive fuera de la estación (es un programa más de tu ordenador). Atril puede arrancarlo
cuando hace falta y, en ese caso, también pararlo; un Ollama que abriste tú nunca se toca.
