# Esquemas de configuración

Dos ficheros TOML, validados por `atril validar`. Las claves van en español; una clave
desconocida es un error (detecta erratas). Ejemplos completos en [`ejemplos/`](ejemplos/).

## `atril.toml` (estación)

La raíz de la estación es la carpeta que contiene `atril.toml`; no se declara dentro.
atril la localiza, por orden: `--estacion`, variable `ATRIL_ESTACION`, o la carpeta actual
y sus superiores.

Estructura fija (no configurable): `app\` (DeepTutor), `data\` (`DEEPTUTOR_HOME`),
`temarios\<id>\`.

| Tabla | Clave | Tipo | Defecto | Notas |
|---|---|---|---|---|
| `[deeptutor]` | `repo` | URL | `https://github.com/HKUDS/DeepTutor` | |
| | `rama` | texto | `"dev"` | |
| | `python` | texto | `"3.13"` | Versión para `app\.venv` |
| | `puertos` | `{ backend, frontend }` | `8001`, `3782` | Distintos, 1–65535 |
| | `parches` | lista de nombres | `[]` | Parches incluidos en atril (`paginas-citas`) |
| | `paquetes` | lista de requisitos | `[]` | Extra en `app\.venv` (p. ej. `claude-agent-sdk`) |
| | `busqueda` | texto | — | Proveedor de búsqueda de DT (`duckduckgo`) |
| `[deeptutor.llm]` (opcional) | `proveedor` | texto | — | Junto con `modelo`; sin claves en el fichero |
| | `modelo` | texto | — | |
| `[ollama]` | `url` | URL | `http://localhost:11434` | |
| | `embedding` | texto | **obligatorio** | |
| | `dimension` | entero ≥ 1 | **obligatorio** | |
| | `contexto` | entero ≥ 1 | `8192` | = `OLLAMA_CONTEXT_LENGTH` y ventana en DT |
| `[indexado]` (opcional) | `parser` | `text_only` · `docling` · `mineru` · `markitdown` · `pymupdf4llm` · `liteparse` · `tika` | `"docling"` | DT usa `text_only` por defecto |
| | `chunk` | entero ≥ 1 | `1024` | |
| | `solape` | entero ≥ 0 | `150` | Menor que `chunk` |
| | `descargar_modelos` | booleano | `true` | Docling/MinerU descargan sus modelos |

`atril instalar` traslada a DeepTutor `[deeptutor.llm]`, `busqueda`, `[ollama]` y los puertos
(`deeptutor config apply`), y `[indexado]` (ajustes internos de parser y chunks). Sustituye a
`setup.json`.
| `[backup]` | `retencion` | `{ diarias, semanales, mensuales }` | `7`, `4`, `12` | `restic forget --keep-*` |
| | `repos_git` | lista de rutas absolutas | `[]` | Git bundle en el snapshot (`D:\…` o `/…`) |
| `[backup.destinos.<nombre>]` | `repo` | texto | **obligatorio** | Repositorio restic; al menos uno |

La contraseña de restic **nunca** va en `atril.toml`: `RESTIC_PASSWORD`,
`RESTIC_PASSWORD_FILE` o `RESTIC_PASSWORD_COMMAND`. Requiere restic 0.17 o posterior (y rclone
para destinos `rclone:`). Un destino local cuya carpeta padre no existe se considera un disco
desconectado y se salta.

## `temario.toml` (temario)

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
| `github` | `kb add-github-source` | Obligatoria | Prohibida | Prohibido |
| `web` | `kb add-web-source` | Obligatoria | Prohibida | Prohibido |

### Ficheros de fuentes

| Ruta (bajo el temario) | Contenido |
|---|---|
| `fuentes\<carpeta>\<archivo>` | Versión vigente, con nombre estable (sin fecha) |
| `fuentes\historico\<carpeta>\<nombre>.<AAAA-MM-DD>.pdf` | Versiones anteriores (fecha de su descarga) |
| `fuentes\registro.json` | Hash SHA-256, tamaño, URL, fecha de descarga y de última comprobación |

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
| `[backup] destinos` → `[backup.destinos.<nombre>]` | La lista duplicaba los nombres de las subtablas |
| Nuevos `[ollama] url`, `contexto` | Lección: el contexto de Ollama debe coincidir con DT |
| Nueva tabla `[indexado]` | Lección: DT usa `text_only` por defecto; chunks 1024/150 |
| Nuevo `[backup] repos_git` | Git bundle del repo de atril (fuera de la estación) |
| Nuevos `titulo`, `archivo`, `descripcion`, `evaluacion` | Fuentes manuales (ISO, PIOT/PGO) y `atril kb evaluar` |
| `comprobar` por defecto `nunca` | Explícito; solo fuentes con `url` |
