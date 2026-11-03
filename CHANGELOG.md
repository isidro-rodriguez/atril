# Changelog

Todos los cambios relevantes de `atril` se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [0.7.1] - 2026-11-03

### Fixed

- Identificación de procesos de DeepTutor: un proceso solo es de la estación si alguno de sus
  argumentos es una ruta **dentro** de la raíz (comparando rutas, sin distinguir mayúsculas ni
  separadores). Antes bastaba con que la ruta apareciera como texto, de modo que un proceso de
  `D:\DeepTutorBackup` contaba como de `D:\DeepTutor` y `atril parar` podía cerrarlo.

### Added

- `scripts/migrar_estacion.py` (no forma parte del paquete): migración de un solo uso de la
  estación anterior (scripts PowerShell) a la estructura de atril, con plan previo y sin borrar
  nada.

## [0.7.0] - 2026-11-03

### Added

- `atril backup [-d destino] [--sin-arrancar]`: copia `atril.toml`, `data/` y `temarios/` con
  restic en cada destino (sin `app/`, que se reconstruye), con un git bundle de cada repo
  (temarios con git y `repos_git`). Para DeepTutor durante la copia y lo vuelve a arrancar,
  crea el repositorio si no existe, muestra el avance y aplica la retención con `--prune`. Un
  disco externo desconectado se salta con un aviso.
- `atril backup comprobar [-d destino] [--datos 5%]`: `restic check` (opcionalmente leyendo
  parte de los datos) y los últimos snapshots de cada destino.
- `atril backup restaurar -d destino [-s snapshot] [--si]`: restaura en una carpeta junto a la
  estación y después intercambia `atril.toml`, `data/` y `temarios/`; lo anterior se conserva
  en `<estación>.previo-<fecha>`. Avisa si el snapshot es de otra ruta, porque las KB guardan
  rutas absolutas.

## [0.6.0] - 2026-11-03

### Added

- `atril kb evaluar <kb> [-k 5] [--dataset f.jsonl] [--detalle]`: sustituye a `evaluar.ps1` y
  `eval_completo.py`. Evalúa la recuperación con el evaluador de DeepTutor comparando con el
  texto completo del chunk (`evidence_text`), no con los 200 caracteres de `content`. Muestra
  avance, una tabla por pregunta (rango del acierto, o lo recuperado en los fallos) y las
  métricas comparadas con el informe anterior de la misma KB, conjunto y `k`. Guarda el
  informe en `temarios/<t>/eval/informes/`, fuera del espacio de trabajo.

## [0.5.0] - 2026-11-03

### Added

- `atril kb indexar <t> [kb]`: sustituye a `indexar.ps1`. Muestra el plan por KB (nueva,
  indexada, cambiada, retirada, sin fichero), comprueba Ollama con un embedding de prueba
  (dimensión y modelos ajenos en VRAM) y añade las fuentes nuevas una a una con
  `deeptutor kb create|add`, con avance (fase, chunks, actividad) y aviso si se cuelga. Cada
  fuente terminada queda en `fuentes/indexado.json`; si se interrumpe, al repetir continúa.
  Las fuentes que DeepTutor ya tenía con el mismo contenido cuentan como indexadas.
- `atril kb reindexar <kb>`: sustituye a `reindexar.ps1`. Arranca DeepTutor si hace falta (o
  lo reinicia si el último indexado dejó el worker atascado), quita por la API las versiones
  anteriores de fuentes cambiadas y las fuentes retiradas del temario, añade las versiones
  nuevas, lanza el reindexado y sigue su progreso hasta el final.

## [0.4.0] - 2026-11-03

### Added

- `atril temario lista`: temarios con número de KB y fuentes, presentes y pendientes.
- `atril temario cobertura <t>`: por KB, cada fuente con su fichero, estado (presente, falta,
  manual, modificada a mano) y última comprobación.
- `atril fuentes descargar <t> [ids]`: sustituye a `descargar-normativa.ps1`. Descarga lo que
  falta con barra de progreso, valida la cabecera `%PDF-`, registra hash y fechas en
  `fuentes/registro.json` e indica dónde colocar las fuentes manuales.
- `atril fuentes comprobar <t> [ids] [--todas]`: vuelve a descargar las fuentes que tocan
  según su frecuencia; si el hash cambia, guarda la versión anterior en `fuentes/historico/` y
  avisa de qué KB hay que reindexar. Un fallo de descarga nunca sustituye el fichero vigente.

## [0.3.0] - 2026-11-03

### Added

- `atril instalar [--sin-docling]`: sustituye a `instalar.ps1` e `instalar-docling.ps1`.
  Comprueba herramientas, clona la rama (superficial, con rutas largas solo en ese repo),
  crea `app/.venv`, instala DeepTutor, paquetes extra y Docling, instala el frontend, descarga
  el modelo de embedding, aplica la configuración (`init` y `config apply`), fija parser y
  chunks, aplica los parches y muestra `deeptutor doctor`. Es re-ejecutable.
- `atril actualizar [--sin-docling] [--sin-arrancar]`: para DeepTutor si está en marcha,
  deshace los parches, trae la última versión de la rama, reinstala dependencias (el frontend
  solo si cambia su lockfile), reaplica los parches y vuelve a arrancar.
- `atril.toml`: `[deeptutor] python`, `paquetes`, `busqueda` y `[deeptutor.llm]`, e
  `[indexado] descargar_modelos`; `parser` se valida contra los motores de DeepTutor. Con
  ellos `atril.toml` sustituye a `setup.json`.
- Aviso al cambiar los chunks: las KB existentes los conservan hasta reindexarlas.

### Changed

- `--home` solo se pasa a los subcomandos de DeepTutor que lo admiten (`doctor` no).
- `arrancar` deja de esperar en cuanto muere el lanzador de DeepTutor (`launcher.json`), por
  ejemplo si falla la compilación del frontend, y muestra el log; antes esperaba hasta agotar
  el tiempo (10 min).
- `parar` no llama a `deeptutor stop` si no hay lanzador en marcha (evita un aviso falso), pero
  sigue cerrando huérfanos.

### Fixed

- `deeptutor doctor` sale con código 1 cuando falla algún check, aunque emite el JSON; atril
  lo trataba como fallo del comando en lugar de mostrar el diagnóstico.

## [0.2.1] - 2026-11-03

### Changed

- La CLI usa Rich en lugar de texto plano: ayuda agrupada en paneles (Configuración,
  DeepTutor), tabla de temarios en `validar`, secciones con símbolos y colores en `estado`,
  indicadores de espera en `arrancar` y `parar`, y el final de `launcher.log` en un panel.
  El texto externo (rutas, mensajes con `[[fuente]]`) se escapa para que Rich no lo
  interprete como markup.
- `rich` pasa a ser dependencia explícita (ya venía con Typer).

## [0.2.0] - 2026-11-03

### Added

- `atril arrancar`: abre Ollama si no responde, avisa de parches pendientes, cierra restos de un
  arranque anterior de la estación, lanza `deeptutor start --detach` y espera a backend y
  frontend; si se agota la espera muestra el final de `launcher.log`.
- `atril parar`: `deeptutor stop` y cierre de los procesos huérfanos de la estación en los
  puertos de DeepTutor; los procesos ajenos se señalan y no se tocan.
- `atril estado`: instalación, servicios, huérfanos, parches y Ollama (versión, modelo de
  embedding, modelos ajenos cargados en VRAM y contexto frente a `OLLAMA_CONTEXT_LENGTH`).
  Termina con código 1 si hay errores.
- `atril parches [--comprobar]`: aplica de forma idempotente los parches de `atril.toml`
  (`paginas-citas`) y detecta cuándo el código de DeepTutor ha cambiado.
- Dependencia `psutil`, para localizar procesos por puerto y cerrar árboles de procesos de
  forma portable.

### Changed

- `[deeptutor] parches` solo admite parches conocidos por atril.
- `DEEPTUTOR_HOME` es la raíz de la estación (como en los scripts actuales); DeepTutor crea
  `data/` dentro. Se corrige la documentación.

## [0.1.2] - 2026-11-03

### Changed

- Requiere `acodo>=0.5.1`, cuyos `has_only_keys` y `has_required_keys` son genéricos en el
  tipo de llave; se elimina el `cast` que hacía falta en `Table.close()`.

## [0.1.1] - 2026-11-03

### Changed

- Requiere `acodo>=0.5`: la validación de rutas relativas de `temario.toml` usa
  `valid_relative_path` y la detección de claves desconocidas usa `has_only_keys`, en lugar
  de implementaciones propias.
- `[backup] repos_git` exige rutas absolutas (`D:\…` o `/…`), validadas con `valid_path`, que
  ya reconoce las de Windows. Los repos que se empaquetan viven fuera de la estación, así que
  resolverlos contra ella no tenía sentido.

### Fixed

- Las rutas relativas que empiezan por `~` (que `to_path` expandiría) ya no se aceptan en
  `carpeta`, `prompt` ni `evaluacion`.

## [0.1.0] - 2026-11-03

### Added

- Esqueleto del proyecto a partir de `acodo-template` 0.3.0 (uv, Ruff, ty, pytest, CI en
  Linux y Windows).
- Esquemas cerrados de `atril.toml` (estación) y `temario.toml` (temarios), con validación
  estricta: tipos, claves desconocidas, reglas por tipo de fuente, pertenencia de cada fuente
  a una sola KB e id de KB únicos en la estación. Documentados en `docs/esquemas.md`.
- CLI `atril` (Typer) con `--estacion` / `ATRIL_ESTACION`, `--version` y `atril validar`.
