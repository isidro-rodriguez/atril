# atril — decisiones de diseño

Herramienta (paquete PyPI `atril`, CLI Typer) para gestionar una instalación local de DeepTutor y sus temarios.
Repo: `isidro-rodriguez/atril` (creado; base: `acodo-template`). Nombre reservado en PyPI. Instalación de uso diario: `uv tool install atril`.
Uso personal: comandos, mensajes y docs en español; código e identificadores en inglés (convención de la plantilla).

## Estructura de la estación (`D:\Desarrollo\DeepTutor\`)

| Carpeta | Contenido | Versionado | Backup |
|---|---|---|---|
| `app\` | Checkout de DeepTutor (HKUDS, rama dev), `.venv`, `node_modules` | git de HKUDS + parches de atril | No (reconstruible) |
| `data\` | Datos de DT: ajustes, KB, índices, `parse_cache`, chats (`DEEPTUTOR_HOME` = raíz de la estación) | — | Sí (prioridad) |
| `temarios\<t>\` | `temario.toml`, `prompt.md`, `espacio\` (único registrado en DT), `fuentes\` (+ `historico\`), `eval\` | git propio solo texto | Sí (PDF e histórico) |
| `atril.toml` | Configuración de la estación | — | Sí |

El código de atril vive en su repo (`D:\Desarrollo\Repositorios\atril`), nunca dentro de la estación.

## Principios

- DeepTutor nunca entra en el `uv.lock` de atril: se controla por su CLI (`app\.venv\Scripts\deeptutor.exe`) y su API (`localhost:8001`). Excepción: la evaluación con texto completo se ejecuta con el Python de `app\`.
- Fuentes fuera del espacio: el agente usa la KB; lo no indexado se busca en web (dominios oficiales, regla del prompt).
- Tipos de fuente: `pdf` (URL → `kb add`), `markdown` (`kb add --docs-dir`), `github` (`kb add-github-source`), `web` (`kb add-web-source`). `github`/`web` sin probar aún.
- Guías no vinculantes en KB separada de la norma vinculante.
- Indexado documento a documento, con registro propio (`fuentes\indexado.json`) y reanudación; quitar o cambiar documentos exige reindexar (DT no purga vectores y guarda una versión nueva con el mismo nombre como `nombre (2).pdf`; el reindexado se fuerza enviando `embedding_model` = selección activa). `kb indexar` solo añade fuentes nuevas; `kb reindexar` quita versiones anteriores y retiradas por la API, añade las nuevas y reindexa.
- Backup con restic: disco externo (conectado solo durante la copia) + Google Drive vía rclone, carpeta por defecto `Atril/`. Retención 7 diarias / 4 semanales / 12 mensuales. Git bundle de los repos dentro del snapshot. Parar DT antes de copiar (SQLite). Restaurar en la misma ruta (rutas absolutas en `kb_config.json`).
- Interfaz: CLI Typer primero; TUI Textual solo si aporta comodidad real.
- README esquemático; detalle en `CLAUDE.md` y `docs/`.
- Entrega del código: commits directos a `main` del repo en GitHub.

## Esquemas (cerrados en fase 0)

Referencia completa, reglas y cambios respecto al borrador en [`esquemas.md`](esquemas.md);
ejemplos en [`ejemplos/`](ejemplos/). Resumen de decisiones:

- La raíz de la estación es la carpeta de `atril.toml` (sin clave `raiz`); se localiza con
  `--estacion`, `ATRIL_ESTACION` o buscando hacia arriba desde la carpeta actual.
- Destinos de backup como `[backup.destinos.<nombre>]`; contraseña de restic solo por entorno.
- `[ollama] contexto` y `[indexado]` (parser, chunk, solape) recogen las lecciones de la
  instalación previa.
- Fuente `pdf` sin `url` = fuente manual (ISO, PIOT/PGO…); `comprobar` exige `url`.
- Cada fuente en exactamente una KB; id de KB únicos en toda la estación.

## Comandos (en español)

| Grupo | Comandos |
|---|---|
| DeepTutor | `atril instalar` · `atril actualizar` · `atril arrancar` · `atril parar` · `atril estado` · `atril parches` |
| Temarios | `atril temario lista` · `atril temario cobertura <t>` |
| Fuentes | `atril fuentes descargar <t>` · `atril fuentes comprobar <t>` |
| KB | `atril kb indexar <t> [kb]` · `atril kb reindexar <kb>` · `atril kb evaluar <kb>` |
| Backup | `atril backup` · `atril backup comprobar` · `atril backup restaurar` |
| Configuración | `atril validar` (fase 0) |
| Otros | `atril accesos` (accesos directos) |

## Fases

0. ✅ Cerrar esquemas `atril.toml` y `temario.toml`; esqueleto desde `acodo-template`; `atril validar`.
1. ✅ Núcleo: config, control de DT (instalar/actualizar/arrancar/parar/estado, huérfanos, parches), comprobación de Ollama. `atril.toml` sustituye a `setup.json`.
2. Temarios: fuentes (descarga/actualización con hash e histórico), KB, evaluación.
3. Backup y restauración.
4. Migración de la estructura actual (`deeptutor_app` → `app`, `materia_normativa` → `temarios\normativa`).
5. Publicación en PyPI y accesos directos.
6. TUI (opcional).

## Estado actual de la instalación (a 2026-11-03)

- Estación: `D:\Desarrollo\DeepTutor\` con `deeptutor_app\` (DT dev v1.7.1, uv, Python 3.13), `data\`, `lanzador\`, `materia_normativa\` (espacio "Normativa" registrado), `evaluaciones\normativa\`.
- LLM: `claude_code` (Claude Code + plan Pro, OAuth), modelo `claude-code/opus`. Embedding: Ollama `qwen3-embedding:8b`, 4096 dim. Chunks 1024/150. Parser: Docling (sin `format-video`).
- KB: `norm-edificacion-cte` (13 PDF vinculantes; eval 35 preguntas: recall@5 1,0, MRR 0,986) y `norm-edificacion-cte-guias` (4 guías). Pendientes: REBT, administrativo, urbanismo (Ley 4/2017 Canarias), Código Estructural (2000 págs, de noche). Fase 2 manual: reglamentos canarios 2018, PIOT/PGO, guía REBT, ISO 9001/14001/45001.
- Qwen 3.5 9B (Ollama) solo para usos triviales, no normativa.
- Scripts PowerShell 7 a portar a atril: `lanzador\` (`instalar.ps1`, `instalar-docling.ps1`, `deeptutor-launcher.ps1`, `aplicar-parches.ps1`, `indexar.ps1`, `reindexar.ps1`), `materia_normativa\descargar-normativa.ps1`, `evaluaciones\normativa\` (`evaluar.ps1`, `eval_completo.py`, `cte-v2.jsonl`, `ampliar-cte.ps1`, `separar-guias.ps1`, `purgar-guias.ps1`).

## Lecciones de la instalación previa

- Ollama: otro cliente puede expulsar el modelo de embedding de la VRAM (8 GB) y la recarga fallar (CUDA error); comprobar antes de indexar y avisar de otros modelos cargados.
- Tras un indexado fallido, el worker queda atascado en el servidor: reiniciar DT antes de reintentar.
- `deeptutor stop` solo para el lanzador; cerrar también procesos huérfanos en 8001/3782 (comprobando su línea de comandos).
- `OLLAMA_CONTEXT_LENGTH` (8192) debe coincidir con la ventana de contexto declarada en DT; DT supone 64K para `qwen`.
- `kb eval` compara solo 200 caracteres por chunk; evaluar con `evidence_text`.
- El símbolo "≥" de las tablas del CTE no existe en la capa de texto del PDF (fuente de símbolos).
- Parche local: citas sin página (`page_label` vacío) en `llamaindex/pipeline.py`.
- Lockfile web de DT apunta a `registry.npmmirror.com`; `npm ci --replace-registry-host`.
- `docling-slim[format-video]` exige compilar `webrtcvad` en Windows; instalar sin ese extra.
- Docling no informa progreso por página; DT por defecto usa parser `text_only` y no descarga modelos de Docling (hay que activarlo).
- La KB se activa por chat (icono de base de datos); asignarla al espacio solo limita la lista.
- Lo que está dentro del espacio de trabajo lo lee el agente (contaminó respuestas con ficheros de evaluación).
