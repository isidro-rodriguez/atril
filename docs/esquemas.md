# Esquemas de configuración

Dos ficheros TOML, validados por `atril validar`. Las claves van en español; una clave
desconocida es un error (detecta erratas). Ejemplos completos en [`ejemplos/`](ejemplos/).

## `atril.toml` (estación)

La raíz de la estación es la carpeta que contiene `atril.toml`; no se declara dentro.
Hay una sola estación por equipo, guardada en la variable de usuario `ATRIL_ESTACION`
(Windows: en el registro del usuario; sin fichero de configuración propio). En la
primera ejecución, con un terminal, atril ofrece la carpeta actual si tiene `atril.toml`; si no,
pregunta la ruta y, si allí no hay `atril.toml`, ofrece inicializarla con un `atril.toml` mínimo
y `temarios\`.

Estructura fija (no configurable): `app\` (DeepTutor), `data\` (`DEEPTUTOR_HOME`),
`temarios\<id>\`. Mientras dura una operación larga (backup, restauración, instalación,
actualización, indexado) existe `.atril.lock` en la raíz: otra no puede empezar hasta que termine.
Si el proceso que lo creó ya no existe, se sustituye.

| Tabla | Clave | Tipo | Defecto | Notas |
|---|---|---|---|---|
| `[deeptutor]` | `repo` | URL | `https://github.com/HKUDS/DeepTutor` | |
| | `rama` | texto | `"dev"` | |
| | `python` | texto | `"3.13"` | Versión para `app\.venv` |
| | `puertos` | `{ backend, frontend }` | `8001`, `3782` | Distintos, 1–65535 |
| | `parches` | lista de nombres | `[]` | Parches incluidos en atril (`paginas-citas`, `arranque-sin-ventana`) |
| | `paquetes` | lista de requisitos | `[]` | Extra en `app\.venv` (p. ej. `claude-agent-sdk`) |
| | `busqueda` | texto | — | Proveedor de búsqueda de DT (`duckduckgo`) |
| `[deeptutor.llm]` (opcional) | `proveedor` | texto | — | Junto con `modelo`; sin claves en el fichero |
| | `modelo` | texto | — | |
| `[ollama]` (opcional) | `url` | URL | `http://localhost:11434` | Sin `[ollama]` DeepTutor funciona (LLM en la nube), pero no se indexan fuentes: `kb indexar`, `reindexar` y `evaluar` lo piden |
| | `embedding` | texto | **obligatorio** en `[ollama]` | |
| | `dimension` | entero ≥ 1 | **obligatorio** en `[ollama]` | |
| | `contexto` | entero ≥ 1 | `8192` | = `OLLAMA_CONTEXT_LENGTH` y ventana en DT |
| `[indexado]` (opcional) | `parser` | `text_only` · `docling` · `mineru` · `markitdown` · `pymupdf4llm` · `liteparse` · `tika` | `"docling"` | DT usa `text_only` por defecto |
| | `chunk` | entero ≥ 1 | `1024` | |
| | `solape` | entero ≥ 0 | `150` | Menor que `chunk` |
| | `descargar_modelos` | booleano | `true` | Docling/MinerU descargan sus modelos |
| | `lote_embedding` | entero ≥ 1 | `10` | Fragmentos por petición de embedding; lotes pequeños = ráfagas de GPU cortas |
| | `pausa_embedding` | entero ≥ 0 | `0` | Milisegundos mínimos entre el inicio de dos peticiones de embedding; con un lote pequeño deja huecos libres a la GPU |
| | `hilos` | entero ≥ 0 | `0` | Hilos de CPU del parser y el troceado al indexar; `0` = sin límite. No cambia el resultado, solo el ritmo |

`atril instalar` traslada a DeepTutor `[deeptutor.llm]`, `busqueda`, `[ollama]` y los puertos
(`deeptutor config apply`), y `[indexado]` (ajustes internos de parser, chunks y ritmo del
embedding). `atril kb indexar` vuelve a aplicar `[indexado]` antes de empezar. Sustituye a
`setup.json`.
| `[backup]` | `destinos` | lista de rutas absolutas | **obligatorio** | Carpetas para las copias; fuera de la estación. Un disco desconectado se salta |
| | `formato` | `zip` · `tar.xz` | `"zip"` | `zip` (deflate 9) o `tar.xz` (xz 9: más compacto, bastante más lento) |
| | `conservar` | entero ≥ 1 | `7` | Copias que se guardan en cada destino; las más antiguas se borran |

Cada copia es `atril-AAAAMMDD-HHMMSS.zip` (o `.tar.xz`) con `atril.toml`, `data\` (sin
`data\atril\logs\`) y `temarios\`, más `atril-backup.json` con la ruta de la estación. Se escribe
como `.part`, se verifica y después se copia al resto de destinos.

## `temario.toml` (temario)

`atril temario crear <nombre>` genera uno nuevo con una sola KB (mismo id que el temario,
`fuentes = ["*"]`, no vinculante) y `prompt.md`. `atril fuentes añadir <temario> <pdf|url>`
añade una `[[fuente]]` pdf (un fichero local se copia a `fuentes\<kb>\` y queda manual; una URL
se descarga con `fuentes descargar`) y, si la KB no la selecciona, añade su id a `fuentes` de la
KB. El fichero se edita conservando comentarios y orden, y se valida antes de sustituirlo.

Ruta: `temarios\<id>\temario.toml`. El id del temario es el nombre de la carpeta (slug).

| Tabla | Clave | Tipo | Defecto | Notas |
|---|---|---|---|---|
| `[temario]` | `nombre` | texto | **obligatorio** | |
| | `prompt` | ruta relativa | `"prompt.md"` | |
| | `dominios_web` | lista de dominios | `[]` | Búsqueda web permitida |
| `[[kb]]` | `id` | slug | **obligatorio** | Único en toda la estación (DT es global) |
| | `vinculante` | booleano | **obligatorio** | Norma y guías en KB distintas |
| | `fuentes` | lista de patrones | **obligatorio** | `fnmatch` sobre id de fuente (`cte-*`) |
| | `descripcion` | texto | — | |
| | `evaluacion` | ruta relativa | — | JSONL de preguntas (`eval/…`); informes en `eval\informes\` |
| `[[fuente]]` | `id` | slug | **obligatorio** | Único en el temario |
| | `tipo` | `pdf` · `markdown` · `github` · `web` | **obligatorio** | |
| | `titulo` | texto | — | |
| | `url` | URL | — | Ver reglas por tipo |
| | `carpeta` | ruta relativa | — | Bajo `fuentes\`; solo `pdf`/`markdown` |
| | `archivo` | nombre `.pdf` | Nombre de la URL | Solo `pdf` |
| | `comprobar` | `nunca` · `semanal` · `mensual` | `"nunca"` | Requiere `url` |

### Reglas por tipo de fuente

| `tipo` | Comando DT | `url` | `carpeta` | `archivo` |
|---|---|---|---|---|
| `pdf` | `kb add` | Opcional: sin ella es **manual** (se coloca a mano) | Obligatoria | Obligatorio si no hay `url` |
| `markdown` | `kb add --docs-dir` | Prohibida | Obligatoria | Prohibido |
| `github` (experimental) | `kb add-github-source` | Obligatoria | Prohibida | Prohibido |
| `web` (experimental) | `kb add-web-source` | Obligatoria | Prohibida | Prohibido |

### Ficheros de fuentes

| Ruta (bajo el temario) | Contenido |
|---|---|
| `fuentes\<carpeta>\<archivo>` | Versión vigente, con nombre estable (sin fecha) |
| `fuentes\historico\<carpeta>\<nombre>.<AAAA-MM-DD>.pdf` | Versiones anteriores (fecha de su descarga) |
| `fuentes\registro.json` | Hash SHA-256, tamaño, URL, fecha de descarga y de última comprobación. Si está dañado, atril se detiene y no lo sobrescribe |

`atril fuentes comprobar` revisa las fuentes según `comprobar` (`semanal`: 7 días, `mensual`: 30)
desde su última comprobación; `--todas` o ids explícitos fuerzan la revisión.

### Pertenencia fuente ↔ KB

- Cada fuente debe pertenecer a **exactamente una** KB (error si a ninguna o a varias).
- Un patrón que no selecciona ninguna fuente es un **aviso** (KB declarada antes que sus
  fuentes, p. ej. REBT pendiente).

## Cambios respecto al borrador

| Cambio | Motivo |
|---|---|
| Fuera `[estacion] raiz` | Se deduce de la ubicación de `atril.toml`; evita incoherencias |
| Nuevos `[ollama] url`, `contexto` | Lección: el contexto de Ollama debe coincidir con DT |
| Nueva tabla `[indexado]` | Lección: DT usa `text_only` por defecto; chunks 1024/150 |
| Nuevos `titulo`, `archivo`, `descripcion`, `evaluacion` | Fuentes manuales (ISO, PIOT/PGO) y `atril kb evaluar` |
| `comprobar` por defecto `nunca` | Explícito; solo fuentes con `url` |
