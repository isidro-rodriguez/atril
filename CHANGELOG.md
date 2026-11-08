# Changelog

Todos los cambios relevantes de `atril` se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [0.23.0] - 2026-11-08

Rediseño de la ventana (`atril-gui`) para que un alumno sin experiencia en consola la use sola.

### Added

- Navegación lateral con siete apartados: Inicio, Temarios, Biblioteca, Servicios, Copias,
  Diagnóstico y Ajustes; cabecera con el estado general y panel de actividad plegable (se pliega
  solo en ventanas estrechas).
- Inicio: estado general con icono por nivel, última actividad y última copia, accesos rápidos y
  temarios modificados recientemente.
- Biblioteca: todas las fuentes de todos los temarios en una tabla, con búsqueda sin tildes y
  filtro por temario; añadir PDF o URL, descargar lo que falta y buscar versiones nuevas.
- Temarios: renombrar y eliminar. Eliminar mueve el temario a `temarios/.papelera/` (no se borra);
  una casilla aparte borra también sus KB en DeepTutor.
- Servicios: DeepTutor, Ollama y herramientas en lenguaje llano; instalar y actualizar DeepTutor.
- Diagnóstico: informe técnico copiable (rutas, versiones, herramientas), `doctor`, parches,
  validar, volver a un commit, abrir registros y el historial completo con el detalle de cada
  operación.
- Ajustes: destinos, formato y retención de copias y ritmo del indexado sin editar TOML; se
  valida antes de guardar y se conservan los comentarios de `atril.toml`.
- Actividad estructurada: cada operación es un evento con resumen y detalle, guardado en
  `data/atril/actividad.jsonl` para conservar el historial entre sesiones.
- Logotipo propio, iconos Lucide (ISC) y fuente Inter (OFL) incluidos en el paquete; Inter se
  registra solo para atril en Windows.

### Changed

- El apartado Administración se reparte entre Servicios (uso diario) y Diagnóstico (técnico).
- `load_syllabi` ignora las carpetas ocultas de `temarios/` (la papelera).

### Fixed

- sv-ttk volvía a aplicar su paleta tras configurar estilos y pisaba los fondos de la ventana.

## [0.22.0] - 2026-11-08

Correcciones de la revisión externa de la 0.21.0, antes del rediseño de la GUI.

### Fixed

- Cerrar la ventana con una operación en marcha ya no la corta: se le pide que pare en un punto
  seguro (o se espera a que termine) y la ventana se cierra después.
- Una copia con ficheros sin leer quedaba como copia normal: contaba para `conservar` y podía
  restaurarse. Ahora se guarda como `atril-…-incompleta`, fuera de la retención y de la
  restauración, y `backup comprobar` avisa de ellas.
- La verificación contrasta la copia con el inventario del manifiesto (nombres y tamaños), no solo
  el CRC del zip o el flujo del xz.
- Un manifiesto con estructura o tipos incorrectos daba una traza de Python; ahora se valida
  estrictamente y es un error claro. Las copias anteriores (sin inventario) siguen valiendo.
- La restauración vuelve a comprobar que DeepTutor está parado justo antes del intercambio.
- Si el intercambio falla y no se puede deshacer del todo, ya no se borra la carpeta extraída.
- Los enlaces simbólicos y uniones ya no se copian (podían meter ficheros de fuera de la estación).
- Dos copias en el mismo segundo ya no se pisan (`-2`, `-3`...).
- Las copias en los demás destinos también se verifican; si una falla no se borran antiguas.
- El bloqueo de la estación usa el bloqueo del sistema (`msvcrt`/`fcntl`): dos procesos ya no
  pueden quedarse a la vez con un bloqueo abandonado.

### Changed

- El manifiesto de las copias añade `completa` y el inventario de ficheros.

## [0.21.0] - 2026-11-08

Fase 5: todo lo necesario para instalar y mantener la estación sin consola.

### Added

- Apartado **Copias** en `atril-gui`: lista de copias de cada destino, «Hacer copia ahora» (con
  Cancelar), «Comprobar copias» y «Restaurar…» (la elegida o la más reciente, con confirmación;
  una copia de otra ruta se acepta expresamente).
- Apartado **Administración**: instalar o completar DeepTutor (Docling opcional), actualizar,
  volver a un commit, aplicar parches y diagnóstico; estado de git, uv, Node.js y Ollama con
  «Instalar lo que falta» mediante `winget` (recarga el PATH sin reabrir atril); abrir y validar
  `atril.toml` y abrir la carpeta de logs.

### Changed

- Instalar, actualizar, parches, validar y diagnóstico pasan a `atril.ops.installation`; la CLI
  los usa igual. `atril actualizar` vuelve a arrancar DeepTutor desde la misma operación.
- Todas las operaciones largas reservan la estación desde `ops`.

## [0.20.0] - 2026-11-08

Fase 4: el alumno gestiona sus temarios desde la ventana.

### Added

- Apartado **Temarios** en `atril-gui`: lista de temarios, «Nuevo temario…», tabla de fuentes
  con su estado de indexado (por indexar, indexada, cambiada, sin fichero) y botones para añadir
  PDF (uno o varios) o una URL (se descarga al momento), descargar, buscar versiones nuevas,
  indexar y reindexar. Los botones que tocan se resaltan y «Cancelar» para en un punto seguro.
- La actividad es común a todos los apartados.

### Changed

- Descarga, comprobación de versiones, estado, indexado y reindexado de KB pasan a `atril.ops`
  (`ops.sources`, `ops.knowledge`); la CLI los usa sin cambios de comportamiento. Las esperas
  largas se actualizan en el mismo indicador (minutos y fase del indexado, tamaño descargado) y
  la descarga muestra el tamaño en el spinner en lugar de una barra.
- El indexado y el reindexado reservan la estación desde `ops`, también desde la ventana.
- Los avisos de KB pendientes dicen «hay que reindexarla» sin nombrar el comando, porque también
  los lee el alumno en la ventana.

## [0.19.0] - 2026-11-08

Fase 3: primera interfaz gráfica, para usar atril sin consola.

### Added

- `atril-gui`: ventana con el estado real de la estación (DeepTutor, Ollama, espacio libre y
  última copia), accesos para abrir DeepTutor en el navegador (lo arranca si hace falta), pararlo,
  volver a comprobar y abrir la carpeta de la estación, y un registro de actividad. Las
  operaciones van en segundo plano: la ventana nunca se queda congelada y los errores se muestran
  con el final del log de DeepTutor.
- Primera ejecución gráfica: se elige la carpeta de la estación o se crea una nueva.
- Al cerrar con DeepTutor en marcha se pregunta si pararlo.
- Icono de atril (PNG y `.ico`) incluido en el paquete.
- Dependencia `sv-ttk` (tema Sun Valley, aspecto de Windows 11, sin dependencias propias).

## [0.18.0] - 2026-11-08

Fase 2 de la interfaz gráfica: un alumno puede crear sus temarios sin editar TOML a mano.

### Added

- `atril temario crear <nombre> [--id]`: temario nuevo con `temario.toml`, `prompt.md`,
  `fuentes/` y una KB que recoge todas sus fuentes.
- `atril fuentes añadir <temario> <pdf|url> [--id] [--titulo] [--kb]`: copia un PDF local a
  `fuentes/<kb>/` o declara una URL. Comprueba que el fichero es un PDF, numera ids repetidos y,
  si la KB no selecciona la fuente, añade su id. `temario.toml` conserva comentarios y orden y se
  valida antes de sustituirlo.
- Dependencia `tomlkit`: `tomllib` solo lee y regenerar el fichero borraría los comentarios.

### Changed

- `[ollama]` es opcional en `atril.toml`. Sin ella DeepTutor funciona (con un LLM en la nube) y
  `arrancar` no busca Ollama; `kb indexar`, `reindexar` y `evaluar` explican que hace falta. Una
  estación nueva la trae comentada.

## [0.17.0] - 2026-11-08

Fase 1 de la interfaz gráfica: la lógica se separa de la CLI para que la GUI la reutilice.

### Added

- Bloqueo de la estación (`.atril.lock` en la raíz) durante backup, restauración, instalación,
  actualización e indexado: la CLI y la futura GUI no pueden pisarse. Un bloqueo de un proceso
  que ya no existe se sustituye solo.
- Una copia de seguridad puede cancelarse entre fichero y fichero sin dejar nada a medias
  (lo usará la GUI).

### Changed

- Arrancar, parar, estado y las copias de seguridad pasan a `atril.ops`, sin Rich ni Typer; los
  comandos solo muestran el resultado. La salida de la CLI no cambia salvo detalles de redacción.
- Todos los errores de atril derivan de `AtrilError`, que puede llevar el final de un log.
- `ATRIL_ESTACION` se guarda directamente en el registro del usuario en lugar de con `setx`.
- Sin consola propia (GUI), los programas que lanza atril se abren sin ventana de consola.

## [0.16.0] - 2026-11-08

Selección de las funcionalidades sugeridas por GPT (las de git y rclone ya no aplican).

### Added

- `atril actualizar --commit <sha>` lleva DeepTutor a ese commit: vuelta atrás cuando la rama
  `dev` rompe algo. Tras cada actualización se muestra el comando para volver a la anterior.
- `atril estado` muestra el espacio libre de la estación y de los destinos de backup, la
  antigüedad de la última copia y las carpetas `.restaurar-*` (restauración interrumpida) o
  `.previo-*` que hayan quedado.

### Changed

- Las copias de seguridad llevan vacías las claves de API de DeepTutor (`model_catalog.json`):
  sin restic ya no van cifradas y no deben acabar en Google Drive. Restaurar avisa de que hay
  que volver a escribirlas; el fichero original no se toca.
- `atril backup comprobar` exige que la copia contenga `atril.toml`, `data/` y `temarios/` y
  avisa si la última tiene más de una semana.

## [0.15.1] - 2026-11-08

Segunda revisión externa (las partes de git bundles ya no aplican).

### Fixed

- Procesos: las rutas se normalizan resolviendo `.` y `..` antes de compararlas, así que
  `DeepTutor\..\DeepTutorBackup\app\python` ya no cuenta como proceso de la estación.
- `registro.json` e `indexado.json` se validan de forma estricta: versión 1, sección obligatoria,
  sin claves desconocidas y con tipos exactos (`"false"` no se toma por `false`). Un fichero que
  no cumple da error y nunca se lee como vacío ni se sobrescribe.
- `atril backup restaurar` comprueba antes de tocar nada que la copia contiene un `atril.toml`
  válido y que las carpetas `.restaurar-*` y `.previo-*` no existen, sin trazas de Python.
- `deeptutor doctor` con comprobaciones de formato inesperado, o ajustes internos que no
  devuelven un objeto, dan un error explicativo.
- `atril instalar` sobre un `app/` existente comprueba antes que sigue el repo y la rama de
  `atril.toml`.

## [0.15.0] - 2026-11-08

### Changed

- `atril backup` crea copias comprimidas `atril-AAAAMMDD-HHMMSS.zip` (deflate 9) o `.tar.xz`
  (xz 9) en las carpetas de `[backup] destinos` (disco externo, Google Drive para escritorio...),
  con solo la biblioteca estándar. Las KB ocupan varios GB y restic + rclone exigían instalar y
  configurar demasiado para esta aplicación. Cada copia se escribe como `.part`, se verifica
  entera y se copia al resto de destinos; se conservan `conservar` copias por destino y no se
  borra ninguna si falta algún fichero o falla una copia.
- `[backup]` pasa a `destinos` (lista de carpetas), `formato` (`zip` o `tar.xz`) y `conservar`.
  Hay que actualizar `atril.toml`: `atril validar` señala las claves antiguas.
- `atril backup restaurar [COPIA]` restaura la copia indicada o la más reciente; `--nueva-ruta`
  sigue siendo obligatoria para una copia hecha desde otra ruta. `backup comprobar` lista las
  copias de cada destino y verifica la más reciente.

### Removed

- restic, rclone y los git bundles (`repos_git`), con las opciones `--destino` y `--snapshot`.
- `scripts/backup.py` (`poe backup`) y `scripts/migrar_estacion.py`: la migración de la estación
  antigua ya está hecha.

## [0.14.1] - 2026-11-04

### Changed

- README: instrucciones mínimas para instalar restic (y rclone para Google Drive) y guardar la
  contraseña de los repositorios fuera de `atril.toml`.

## [0.14.0] - 2026-11-04

### Changed

- Una sola estación por equipo, guardada en la variable de usuario `ATRIL_ESTACION`. La primera
  ejecución ofrece la carpeta actual si tiene `atril.toml`; si no, pregunta la ruta y, si allí
  no hay `atril.toml`, ofrece inicializar la estación (`atril.toml` mínimo y `temarios/`). Las
  preguntas se contestan con s/n.
- En Windows, si el terminal se abrió antes del `setx`, la estación se lee del registro del
  usuario: ya no vuelve a preguntar en el mismo terminal.

### Removed

- Opción `--estacion` y búsqueda de `atril.toml` en carpetas superiores: con una sola estación
  por equipo sobraban.

## [0.13.0] - 2026-11-04

### Added

- Primer uso fuera de la estación: si no hay `--estacion`, `ATRIL_ESTACION` ni `atril.toml` en la
  carpeta actual o sus superiores y hay un terminal, atril pregunta la ruta, comprueba que
  contiene `atril.toml` y la guarda como variable de usuario `ATRIL_ESTACION` (`setx` en Windows).
  Así se puede usar desde cualquier carpeta sin un fichero de configuración propio. Sin terminal
  (scripts, tareas programadas) sigue fallando con el mensaje de siempre.

## [0.12.1] - 2026-11-04

### Fixed

- `atril kb indexar` mezclaba el run de un indexado anterior con el actual: avisaba de "sin
  actividad desde hace N min" nada más empezar y, si el nuevo fallaba antes de crear su run,
  mostraba el error del viejo. Ahora solo cuenta el run de este indexado y, si no hay, el motivo
  sale del log de DeepTutor.
- Si la KB no tiene índice listo porque un indexado anterior quedó a medias, el error dice que
  hay que ejecutar `atril kb reindexar <kb>` en lugar de sugerir repetir el mismo comando.

## [0.12.0] - 2026-11-03

### Added

- `[indexado] lote_embedding` y `pausa_embedding`: tamaño de lote e intervalo mínimo (ms) entre
  peticiones de embedding, aplicados al perfil activo de DeepTutor (`batch_size`/`batch_delay`).
  Con la GPU al 100 %, lotes pequeños con pausa dejan huecos al escritorio; los vectores son los
  mismos, solo cambia el ritmo.

### Changed

- `atril kb indexar` vuelve a aplicar `[indexado]` a DeepTutor antes de empezar: un cambio en
  `atril.toml` vale sin reinstalar.

## [0.11.0] - 2026-11-03

### Added

- `[indexado] hilos`: límite de hilos de CPU (PyTorch, NumPy, Docling) para el indexado; `0`
  (por defecto) es sin límite. Cambia el ritmo, no el resultado.
- Aviso antes de indexar si el modelo de embedding no cabe entero en la VRAM: la parte que va a
  la CPU satura el procesador.

### Changed

- `atril kb indexar` lanza el CLI de DeepTutor con prioridad baja de CPU y de disco (la heredan
  sus procesos hijos). Con el equipo libre va igual de rápido; cuando se usa, cede el turno y el
  equipo sigue respondiendo.

## [0.10.0] - 2026-11-03

### Added

- `atril kb estado [temario] [kb] [--detalle]`: tabla por KB con las fuentes indexadas,
  nuevas, cambiadas, sin fichero y retiradas (cada una cuenta en una sola columna), y el
  estado del último indexado de DeepTutor (en marcha, completado, interrumpido...). Solo lee:
  hasta ahora, la única forma de verlo era `kb indexar`, que además se ponía a indexar.

## [0.9.0] - 2026-11-03

### Added

- Parche `arranque-sin-ventana`: en Windows, `deeptutor start --detach` dejaba abierta una
  consola vacía. El `python.exe` del venv es un redirector y, con `DETACHED_PROCESS`, el
  intérprete real recibía una consola nueva y visible; con `CREATE_NO_WINDOW` sigue
  desacoplado del terminal, pero sin ventana. Se activa en `[deeptutor] parches`.

### Changed

- `atril backup restaurar --forzar-otra-ruta` pasa a llamarse `--nueva-ruta`.
- Ayudas de la CLI redactadas para caber en una línea en un terminal de 120 columnas, y
  argumentos con nombres en español (`TEMARIO`, `FUENTES`, `KB`).
- README: guía rápida con la instalación y el uso, un listado comentado de comandos y una
  sección de desarrollo con la calidad.

## [0.8.0] - 2026-11-03

Mejoras de la revisión externa (`revision_GPT.md`) sobre operaciones destructivas y estado.

### Changed

- `atril backup` distingue un backup **incompleto** (restic con ficheros sin leer, código 3, o un
  repo de `repos_git` que no se empaqueta): termina con código 1, nunca dice "Backup terminado" y
  no aplica la retención, para que un snapshot incompleto no desplace a uno completo.
- `atril backup restaurar` exige `--forzar-otra-ruta` para un snapshot hecho desde otra ruta
  (las KB guardan rutas absolutas); `--si` ya no basta.
- `atril actualizar` comprueba que `app/` sigue el repo y la rama de `atril.toml` antes del
  `reset --hard`, reaplica la configuración de DeepTutor, el parser y los chunks, y termina con
  `deeptutor doctor`. Si el venv tiene otra versión de Python, lo recrea.
- `atril instalar` y `atril actualizar` avisan si la versión de DeepTutor no es una probada (1.7).
- Parches: solo son estados limpios el original una vez (pendiente) o el nuevo una vez
  (aplicado); texto repetido o ambos a la vez cuentan como código cambiado.
- `atril temario lista` separa Presentes, Manuales y Faltan (antes una fuente manual contaba
  como presente y como pendiente).
- Se retira `atril accesos` del plan: atril ya es una CLI en el `PATH`.

### Fixed

- Restauración: si el intercambio falla a medias (p. ej. un fichero bloqueado en Windows), se
  deshacen los movimientos y la estación queda como estaba.
- `restic backup` escribe stderr en un fichero temporal: con dos tuberías podía bloquearse.
- `registro.json` o `indexado.json` dañados dan un error claro y no se sobrescriben.
- La evaluación conserva la traza de cada pregunta aunque el dataset repita el texto.
- Un id de temario que no es un slug (p. ej. `../x`) se rechaza en la CLI.
- JSON inesperado de `deeptutor doctor` o de los ajustes internos da un mensaje explicativo.

### Added

- Validaciones de `atril.toml`: repositorio restic dentro de la estación, retención 0/0/0 y dos
  `repos_git` con el mismo nombre de carpeta (sus bundles se pisarían).

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
