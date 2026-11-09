# `temario.toml`

Cada temario se describe en `temarios\<id>\temario.toml`. El id del temario es el nombre de
la carpeta. Lo crean **Nuevo temario** (ventana) y `atril temario crear`, y lo modifican
**Añadir PDF/URL** y `atril fuentes añadir`, conservando comentarios y orden.

## Ejemplo completo

Un temario de normativa de edificación con varias KB y tipos de fuente. Lo validan las
pruebas de atril.

```toml title="temario.toml"
--8<-- "documentacion/ejemplos/temario.toml"
```

[Descargar el ejemplo](ejemplos/temario.toml){ .md-button }

## Cómo se crea y se modifica

`atril temario crear <nombre>` genera uno nuevo con una sola KB (mismo id que el temario,
`fuentes = ["*"]`, no vinculante) y `prompt.md`. `atril fuentes añadir <temario> <pdf|url>`
añade una `[[fuente]]` pdf (un fichero local se copia a `fuentes\<kb>\` y queda manual; una URL
se descarga con `fuentes descargar`) y, si la KB no la selecciona, añade su id a `fuentes` de la
KB. El fichero se edita conservando comentarios y orden, y se valida antes de sustituirlo.

## Claves

| Tabla | Clave | Tipo | Defecto | Notas |
|---|---|---|---|---|
| `[temario]` | `nombre` | texto | **obligatorio** | |
| | `prompt` | ruta relativa | `"prompt.md"` | |
| | `dominios_web` | lista de dominios | `[]` | Búsqueda web permitida |
| `[[kb]]` | `id` | slug | **obligatorio** | Único en toda la estación (DeepTutor las guarda todas juntas) |
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

## Reglas por tipo de fuente

| `tipo` | Comando DT | `url` | `carpeta` | `archivo` |
|---|---|---|---|---|
| `pdf` | `kb add` | Opcional: sin ella es **manual** (se coloca a mano) | Obligatoria | Obligatorio si no hay `url` |
| `markdown` | `kb add --docs-dir` | Prohibida | Obligatoria | Prohibido |
| `github` (experimental) | `kb add-github-source` | Obligatoria | Prohibida | Prohibido |
| `web` (experimental) | `kb add-web-source` | Obligatoria | Prohibida | Prohibido |

## Ficheros de fuentes

| Ruta (bajo el temario) | Contenido |
|---|---|
| `fuentes\<carpeta>\<archivo>` | Versión vigente, con nombre estable (sin fecha) |
| `fuentes\historico\<carpeta>\<nombre>.<AAAA-MM-DD>.pdf` | Versiones anteriores (fecha de su descarga) |
| `fuentes\registro.json` | Hash SHA-256, tamaño, URL, fecha de descarga y de última comprobación. Si está dañado, atril se detiene y no lo sobrescribe |

`atril fuentes comprobar` revisa las fuentes según `comprobar` (`semanal`: 7 días, `mensual`: 30)
desde su última comprobación; `--todas` o ids explícitos fuerzan la revisión.

## Pertenencia fuente ↔ KB

- Cada fuente debe pertenecer a **exactamente una** KB (error si a ninguna o a varias).
- Un patrón que no selecciona ninguna fuente es un **aviso** (KB declarada antes que sus
  fuentes, p. ej. REBT pendiente).

