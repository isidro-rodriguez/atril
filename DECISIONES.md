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
- ~~Backup con restic~~ (sustituido en 0.15.0 por copias zip/tar.xz, ver abajo): disco externo (conectado solo durante la copia) + Google Drive vía rclone, carpeta por defecto `Atril/`. Retención 7 diarias / 4 semanales / 12 mensuales. Git bundle de los repos dentro del snapshot. Parar DT antes de copiar (SQLite). Restaurar en la misma ruta (rutas absolutas en `kb_config.json`).
- Interfaz: CLI Typer para uso avanzado y servidores; GUI tkinter para quien no usa la consola (ver «Interfaz gráfica»). Sin TUI.
- README esquemático; detalle en `CLAUDE.md` y en la web (`docs/`, Zensical).
- Entrega del código: commits directos a `main` del repo en GitHub.

## Esquemas (cerrados en fase 0)

Referencia completa en la web ([`atril.toml`](https://isidro-rodriguez.github.io/atril/documentacion/atril-toml/) y
[`temario.toml`](https://isidro-rodriguez.github.io/atril/documentacion/temario-toml/)); ejemplos, validados por las pruebas, en
`docs/documentacion/ejemplos/`. Cambios respecto al borrador al final de esta sección. Resumen de decisiones:

- La raíz de la estación es la carpeta de `atril.toml` (sin clave `raiz`); se localiza con
  `--estacion`, `ATRIL_ESTACION` o buscando hacia arriba desde la carpeta actual.
- ~~Destinos de backup como `[backup.destinos.<nombre>]`~~ (0.15.0: `[backup] destinos` es una lista de carpetas).
- `[ollama] contexto` y `[indexado]` (parser, chunk, solape) recogen las lecciones de la
  instalación previa.
- Fuente `pdf` sin `url` = fuente manual (ISO, PIOT/PGO…); `comprobar` exige `url`.
- Cada fuente en exactamente una KB; id de KB únicos en toda la estación.


### Cambios de los esquemas respecto al borrador

| Cambio | Motivo |
|---|---|
| Fuera `[estacion] raiz` | Se deduce de la ubicación de `atril.toml`; evita incoherencias |
| Nuevos `[ollama] url`, `contexto` | Lección: el contexto de Ollama debe coincidir con DT |
| Nueva tabla `[indexado]` | Lección: DT usa `text_only` por defecto; chunks 1024/150 |
| Nuevos `titulo`, `archivo`, `descripcion`, `evaluacion` | Fuentes manuales (ISO, PIOT/PGO) y `atril kb evaluar` |
| `comprobar` por defecto `nunca` | Explícito; solo fuentes con `url` |

## Comandos (en español)

| Grupo | Comandos |
|---|---|
| DeepTutor | `atril instalar` · `atril actualizar` · `atril arrancar` · `atril parar` · `atril estado` · `atril parches` |
| Temarios | `atril temario lista` · `atril temario cobertura <t>` |
| Fuentes | `atril fuentes descargar <t>` · `atril fuentes comprobar <t>` |
| KB | `atril kb estado [t] [kb]` · `atril kb indexar <t> [kb]` · `atril kb reindexar <kb>` · `atril kb evaluar <kb>` |
| Backup | `atril backup` · `atril backup comprobar` · `atril backup restaurar` |
| Configuración | `atril validar` (fase 0) |
| Temarios del alumno (0.18.0) | `atril temario crear` · `atril fuentes añadir` |
| GUI (0.19.0) | `atril-gui` |

## Fases

0. ✅ Cerrar esquemas `atril.toml` y `temario.toml`; esqueleto desde `acodo-template`; `atril validar`.
1. ✅ Núcleo: config, control de DT (instalar/actualizar/arrancar/parar/estado, huérfanos, parches), comprobación de Ollama. `atril.toml` sustituye a `setup.json`.
2. ✅ Temarios: fuentes (descarga/actualización con hash e histórico), KB (indexado y reindexado), evaluación con texto completo e informes comparados en `eval\informes\`.
3. ✅ Backup y restauración (`atril backup`, `backup comprobar`, `backup restaurar`). La restauración va a `<estación>.restaurar-<fecha>` y después se intercambia; lo actual queda en `<estación>.previo-<fecha>`.
4. ✅ Migración de la estructura actual con `scripts\migrar_estacion.py` (plan por defecto, `--aplicar` para ejecutar; no borra nada, todo lo sobrante va a `_legado\`): `deeptutor_app` → `app` (venv apartado y recreado con `atril instalar`), `materia_normativa` → `temarios\normativa\espacio` (el historial de chats viaja con la carpeta; el catálogo de espacios de DT se actualiza), fuentes con nombre estable y registros (`registro.json`, `indexado.json`) generados por hash contra `raw\` de cada KB, de modo que no hay que reindexar. Aplicada el 2026-11-03: `kb evaluar norm-edificacion-cte` repite recall@5 1,000 y MRR 0,986.
5. ✅ Publicación en PyPI (`publish.yml`). Los accesos directos se retiran: `atril` ya es una CLI en el `PATH`.
6. ~~TUI (opcional)~~ → GUI tkinter, plan en «Interfaz gráfica».

## Estado actual de la instalación (a 2026-11-03)

- Estación: `D:\Desarrollo\DeepTutor\` con la estructura de atril: `atril.toml`, `app\` (DT dev v1.7.1, uv, Python 3.13), `data\`, `temarios\normativa\` (espacio "Normativa" registrado en `espacio\`, 8 KB declaradas, 33 fuentes: 24 en disco y 9 manuales pendientes). `_legado\` guarda los scripts PowerShell y restos de la estructura anterior hasta borrarlo.
- LLM: `claude_code` (Claude Code + plan Pro, OAuth), modelo `claude-code/opus`. Embedding: Ollama `qwen3-embedding:8b`, 4096 dim. Chunks 1024/150. Parser: Docling (sin `format-video`).
- KB: `norm-edificacion-cte` (13 PDF vinculantes; eval 35 preguntas: recall@5 1,0, MRR 0,986) y `norm-edificacion-cte-guias` (4 guías). Pendientes: REBT, administrativo, urbanismo (Ley 4/2017 Canarias), Código Estructural (2000 págs, de noche). Fase 2 manual: reglamentos canarios 2018, PIOT/PGO, guía REBT, ISO 9001/14001/45001.
- Qwen 3.5 9B (Ollama) solo para usos triviales, no normativa.
- Pendiente: indexar `norm-estructuras` (Código Estructural, de noche); colocar las fuentes manuales (ISO, decretos de Canarias 2018, PIOT/PGO, guía REBT); fuentes `github`/`web` sin uso real todavía (experimentales).

## Revisión externa (`revision_GPT.md`), aplicada en 0.7.1 y 0.8.0

| Riesgo | Decisión |
|---|---|
| Backup con ficheros sin leer (restic 3) o bundle de `repos_git` fallido | **Incompleto**: código 1, sin retención (no desplaza a un snapshot completo) |
| `actualizar` con otro remoto u otra rama en `app/` | Se aborta antes del `reset --hard` |
| Intercambio de restauración a medias | Se deshace; si no puede, lo dice y lo previo queda en `.previo-<fecha>` |
| Snapshot de otra ruta | Exige `--nueva-ruta` (no basta `--si`) |
| `registro.json`/`indexado.json` dañados | Error claro; nunca se sobrescriben |
| Parche con el texto repetido o ambos presentes | `código cambiado`; nunca se fuerza |
| venv con otra versión de Python | `uv venv --clear` y reinstalación |
| `actualizar` sin reaplicar ajustes | Reaplica `config apply`, parser y chunks, y pasa `doctor` |
| Repo restic dentro de la estación, retención 0/0/0, bundles con el mismo nombre | Errores de configuración |
| Preguntas repetidas en la evaluación | Traza por pregunta en orden |
| Versión de DT no probada / JSON de DT distinto | Aviso / error explicativo |
| Fuentes `github`/`web` | Experimentales: sin batería de pruebas hasta tener un uso real |
| 2.ª revisión (0.15.1): `..` en rutas de procesos | Se resuelven `.`/`..` antes de comparar: `DT\..\DTBackup` no es de la estación |
| 2.ª revisión: estados JSON permisivos | Versión, claves y tipos exactos; `"false"` no es `false` |
| 2.ª revisión: restaurar sin estación válida, `keep` existente | Se comprueba antes de intercambiar; nada cambia |
| 2.ª revisión: `doctor` con elementos raros, `instalar` sobre otro checkout | `StepError` y se para |
| 2.ª revisión: git bundles (P1.1, P2.2) | No aplica: backups en zip/tar.xz desde 0.15.0 |

## Funcionalidades sugeridas por GPT (0.16.0)

| Sugerencia | Decisión |
|---|---|
| 5.1 Secretos en copias | ✅ Las claves de API de `model_catalog.json` se vacían en la copia (sin restic ya no hay cifrado); restaurar avisa de reescribirlas |
| 4.1 Versiones y rollback | ✅ `atril actualizar --commit <sha>`; tras actualizar se muestra el comando para volver. atril ya se fija con `uv tool install atril==X` |
| 3.2 / 6.1 doctor y estado | ✅ `atril estado` añade espacio libre (estación y destinos), última copia y restauraciones a medias (lo esencial de 2.3) |
| 2.1 Verificar copias | ✅ `backup comprobar` exige `atril.toml`, `data/` y `temarios/` y avisa si la última tiene más de 7 días |
| 2.2 Ensayo de restauración | ❌ Restaurar ya valida antes de intercambiar, deshace y conserva `.previo-*`; extraer GB para comprobar lo mismo no compensa |
| 2.3 Diario de operaciones | ❌ Las operaciones son repetibles o atómicas; solo se avisa de restauraciones a medias |
| 3.1 Historial, 3.3 Inventario, 4.2 Política | ❌ Auditoría de equipo; para un usuario y una estación no aporta |

## Interfaz gráfica (decidida el 2026-11-08, pendiente de implementar)

Motivo: un alumno sin experiencia con la consola quiere usar atril y crear sus propios temarios.
La CLI se mantiene para usuarios avanzados e instalaciones en servidor. De la propuesta de GPT
(`Interfaz_gráfica_…md`) se descarta lo que supone un motor que atril no tiene: editor de bloques,
unidades y temas, generación asistida, «biblioteca», servicio de notificaciones y «último temario».
El estudio se hace en la web de DeepTutor; la GUI arranca, mantiene y alimenta la estación.

| Tema | Decisión | Descartado |
|---|---|---|
| Tecnología | tkinter + ttk con el tema `sv-ttk` (aspecto Windows 11) | Qt, web embebida, Textual |
| Paquete | Uno solo, `atril`: `atril` (CLI) y `atril-gui` (`[project.gui-scripts]`, sin consola). Desde 0.30.0, `atril gui` lanza la ventana como proceso aparte con `pythonw` y devuelve la consola (un *console script* dejaría la consola ocupada y, al cerrarla, mataría la ventana) | Paquete aparte; solo `atril gui` |
| Núcleo | Nuevo `atril/ops/`: casos de uso sin Rich ni Typer que devuelven resultados o `Finding`, aceptan `progress(done, total, texto)` y un `threading.Event` de cancelación. `commands/` solo traduce argumentos, pinta y fija el código de salida; `gui/` igual con widgets. Los módulos actuales del núcleo no cambian | Capas `domain/`/`infrastructure/`; GUI que llame a la CLI por subprocess |
| Errores | `AtrilError` (y subclases existentes) con mensaje en español; la CLI hace `fail()`, la GUI muestra un diálogo con detalle técnico | `typer.Exit` dentro de la lógica |
| Confirmaciones | Las pide la interfaz antes de llamar a `ops`; nunca dentro de `ops` | |
| Concurrencia | Un hilo de trabajo + `queue.Queue` leída con `after()` (Tk no admite llamadas desde otros hilos). Cancelación solo en puntos seguros (entre fuentes al indexar; antes de renombrar el `.part` de una copia). Bloqueo de estación `<raíz>/.atril.lock` (fuera de copias y restauraciones) para operaciones largas, compartido por CLI y GUI; reentrante en el mismo proceso y sustituible si su proceso ha muerto | |
| Subprocesos | Desde `pythonw` todo `git`/`uv`/`npm`/`deeptutor` se lanza con `CREATE_NO_WINDOW` en Windows; la variable `ATRIL_ESTACION` se escribe en el registro (`winreg`) en lugar de `setx` | |
| Secciones | Inicio (estado real, abrir DeepTutor, parar) · Temarios (temarios, KB, fuentes, descargar, comprobar, indexar) · Copias (crear, comprobar, restaurar con confirmación) · Administración (instalar, actualizar o volver a un commit, parches, validar, doctor, abrir `atril.toml`) · asistente de primera ejecución | Biblioteca, Diagnóstico y Servicios como secciones aparte |
| Temarios del alumno | «Crear temario»: id slug a partir del nombre, `prompt.md` de plantilla, una KB `<id>` con `fuentes = ["*"]` y `vinculante = false`. «Añadir fuente»: PDF local (se copia a `fuentes/<carpeta>/`, fuente manual) o URL. Mismos casos de uso en la CLI: `atril temario crear` y `atril fuentes añadir` | Formato de temario paralelo |
| Escritura de `temario.toml` | `tomlkit`: conserva comentarios y orden (`tomllib` solo lee); se valida con `load_syllabus` antes de guardar y se escribe vía `.nuevo` + renombrado | Regenerar el fichero (borra comentarios) |
| Ollama | `[ollama]` pasa a ser opcional: sin ella no se indexa (`kb indexar`/`reindexar`/`evaluar` lo dicen claramente) y `arrancar` no lo levanta. El LLM puede ser de la nube, con su clave en los ajustes de DeepTutor (nunca en `atril.toml`) | |
| Ajustes | Desde 0.24.0, formulario completo de `atril.toml` en pestañas (ver «Segundo rediseño») | |
| Bandeja | Desde 0.28.0, área de notificación en Windows (ver «Área de notificación»). Antes: no, al cerrar se preguntaba si parar DeepTutor | `pystray` (arrastra Pillow) |
| Icono | `icon.png` del proyecto reducido a 256/64/32 px en `gui/recursos/` y `.ico` para el instalador | Original de 1,4 MB |
| Distribución Windows | Instalador Inno Setup **por usuario** (sin administrador), publicado en las releases de GitHub: lleva `uv.exe`, ejecuta `uv tool install atril`, crea accesos directos con icono. Desinstalar quita programa y accesos, nunca la estación, las copias ni `ATRIL_ESTACION` | PyInstaller: no incluye git, Node.js, Ollama ni DeepTutor |
| Dependencias externas | Al instalar DeepTutor desde la GUI: git y Node.js obligatorios, Ollama opcional. Si faltan, se ofrece `winget` (puede pedir permiso de administrador) o el enlace oficial | Meterlas en el instalador |
| Actualizar atril | Desde 0.31.0, al abrir la ventana (`[atril] buscar_actualizaciones`, por defecto sí) se consulta la última release de GitHub (`ops.updates`). Instalado con el instalador: se descarga el nuevo, se comprueba su SHA-256 (el `digest` de la release), se libera el mutex, se lanza en silencio con `/abrir=si /esperar=<pid>` y la ventana se cierra; el instalador espera a que ese proceso termine (sus ficheros del entorno están en uso), instala (hasta tres intentos) y reabre la ventana. Instalado de otro modo: se ofrece ver las novedades. Sin conexión no se dice nada. La CLI solo avisa, en `atril estado` (Windows no deja sustituir `atril.exe` mientras se ejecuta) | `uv tool upgrade` desde la ventana (Windows bloquea el `.exe` en uso); PyPI como fuente (el instalador llega minutos después) |
| Firma | Sin firma al principio (SmartScreen: «Más información → Ejecutar de todas formas») | Certificado de pago, por ahora |
| Linux/macOS | `uv tool install atril` + `atril-gui`; sin instalador. Nada específico de Windows fuera de adaptadores | |

### Notas de implementación

- `sv-ttk` llama a `tk_setPalette` al procesar `<<ThemeChanged>>`: si se procesa después de crear
  los widgets, pisa sus fondos y los colores de `ttk.Label`. Se procesa antes de construir la
  ventana y los textos van en widgets `tk` con colores explícitos (`style.label`, `style.card`).
- La ventana se valida con capturas en Xvfb; Inter solo se registra en Windows (el Tk de Linux de
  uv no tiene Xft), así que tamaños y glifos se revisan allí. Inter (subconjunto latino) no tiene
  ✓, ✗ ni flechas: se usan iconos.
- Rendimiento (0.23.1): `ttk` repite la imagen de un elemento para rellenarlo; una tarjeta de
  30 px suponía miles de copias por repintado (5 s de arranque, 3 s por redimensionado). Imagen de
  640 px, apartados ocultos con `grid_remove`, datos leídos solo cuando caducan, sondeo rápido de
  puertos locales (Windows tarda ~2 s en rechazar cada dirección de `localhost`) y hash recordado
  de los PDF grandes. Las fuentes con nombre se pierden si se libera su objeto de tkinter.
- Cada `ttk.Style.configure` programa otro `<<ThemeChanged>>` y sv-ttk vuelve a aplicar su paleta
  a los widgets ya creados: los estilos se configuran solo en `style.apply`, que lo procesa al
  final.

### Plan

| Fase | Contenido | Versión |
|---|---|---|
| 1 ✅ | `ops/` para servicio (arrancar, parar, estado) y copias; `AtrilError`; bloqueo de estación; `CREATE_NO_WINDOW`. La CLI pasa a usar `ops` sin cambios visibles | 0.17.0 |
| 2 ✅ | Temarios del alumno en la CLI: `[ollama]` opcional, `temario crear`, `fuentes añadir` (`tomlkit`, `ops.syllabus`). Los `ops` de descarga e indexado pasan a la fase 4, cuando la GUI los use | 0.18.0 |
| 3 ✅ | GUI mínima: primera ejecución, Inicio, abrir y parar DeepTutor, `atril-gui`. Se prueba con el alumno | 0.19.0 |
| 4 ✅ | `ops` de descarga, comprobación, indexado y reindexado; GUI de Temarios (crear, añadir PDF o URL, descargar, buscar versiones, indexar y reindexar con avance y cancelación) | 0.20.0 |
| 5 ✅ | GUI de Copias y Administración (instalar DeepTutor con comprobación de dependencias y `winget`, actualizar, volver a un commit, parches, validar, doctor); `ops.installation` | 0.21.0 |
| 6 | Instalador Inno Setup en las releases (job `windows-latest`), guía del alumno | 1.0.0 |

Pruebas: `ops` con los mismos dobles que hoy (sin tiempo real ni servicios); en la GUI se prueba la
lógica de las vistas y el trabajador sin pantalla; las pruebas que abren ventanas se saltan si no
hay pantalla.

## Revisión de la 0.21.0 y rediseño de la GUI (decidido el 2026-11-08)

### Correcciones (revisión externa, verificada contra el código)

| Problema | Corrección |
|---|---|
| Cerrar la ventana mataba la operación en curso (hilo *daemon*) | Al cerrar con una operación en marcha: se cancela en un punto seguro si es cancelable o se espera a que termine; la ventana no se destruye antes |
| Una copia incompleta quedaba como `atril-*.zip` normal: contaba en la retención y podía restaurarse | Manifiesto con inventario (nombre y tamaño) y `completa`; `verify()` lo contrasta con el archivo; una copia incompleta se renombra `…-incompleta` y queda fuera de la retención y de la restauración. Sin hash por fichero (duplicaría la lectura) |
| Manifiesto sin validar (un JSON lista daba traza) | Validación estricta de claves y tipos → `BackupError`; los manifiestos sin inventario (≤ 0.21) se aceptan como antiguos |
| DeepTutor podía arrancar entre la confirmación y la restauración | Se vuelve a comprobar dentro de `restore()`, con el bloqueo |
| Con el *rollback* incompleto se borraba la carpeta de extracción | Si el estado queda incierto no se borra nada y se indican las rutas |
| Enlaces simbólicos a ficheros de fuera | Se saltan enlaces y uniones, con aviso |
| Dos copias en el mismo segundo se pisaban | Sufijo `-2`, `-3`... |
| Las copias en otros destinos no se verificaban | Se verifica cada una; si falla, no hay retención |
| Bloqueo: dos procesos podían sustituir a la vez uno abandonado | Bloqueo del sistema (`msvcrt`/`fcntl`) sobre `.atril.lock`: el sistema lo libera si el proceso muere |
| Bandeja del sistema | Descartada (ya decidido: arrastra Pillow y no aporta) |

### Rediseño de la GUI

Referencia visual: «Panel educativo Atril en español» (dirección estética, no diseño literal).

| Tema | Decisión |
|---|---|
| Navegación lateral | Inicio, Temarios, Biblioteca, Servicios, Copias, Diagnóstico, Ajustes; logotipo arriba; sin versión (va en la barra inferior) |
| Biblioteca | Todas las fuentes de todos los temarios, con búsqueda y filtros; añadir PDF o URL. No hay apartado «Fuentes» aparte (era redundante) |
| Temarios | Crear, renombrar, eliminar, KB e indexado. **Eliminar** mueve la carpeta a `temarios/.papelera/<id>-<fecha>` y deja las KB en DeepTutor; una casilla aparte borra también las KB (irreversible) |
| Servicios | DeepTutor y Ollama (arrancar, parar, estado), herramientas en lenguaje llano, instalar y actualizar DeepTutor |
| Diagnóstico | Lo técnico: rutas, versiones, `doctor`, parches, logs, historial completo, volver a un commit |
| Ajustes | Edición guiada de pocas claves de `atril.toml` (copias, ritmo de indexado) con `tomlkit` y validación; sin segunda fuente de configuración |
| Actividad | ~~Panel derecho plegable; «Ver todo» en Diagnóstico~~ (sustituido en 0.24.0: apartado Actividad completo). Un evento por operación (título, resumen, nivel, hora, detalle) guardado en `data/atril/actividad.jsonl` |
| Inicio | Estado general, servicios, última copia, accesos rápidos y «Modificados recientemente» (atril no registra el uso de un temario: no se inventa) |
| Logotipo | SVG propio como fuente maestra; PNG a 1× y 2× generados de él (Tk 8.6 no pinta SVG) |
| Tipografía | Inter (OFL) incluida en el paquete y registrada solo para atril en Windows (`AddFontResourceExW` privado); Segoe UI si falla |
| Iconos | Lucide (ISC) rasterizados a PNG en dos tamaños |
| Tarjetas | Esquinas redondeadas con una imagen 9-*slice* como elemento de `ttk` |
| Pantallas | Comprobación a 1366×768 y 1920×1080, escalados 100/125/150 % |
| Descartado | «Generación» de temarios (no existe en atril), bandeja, sesión multiusuario |

| Fase | Contenido | Versión |
|---|---|---|
| A ✅ | Correcciones de la revisión | 0.22.0 |
| B+C ✅ | Base visual (recursos, componentes, navegación, cabecera, actividad estructurada) y apartados nuevos sin perder funciones; publicadas juntas | 0.23.0 |
| B+C+ ✅ | Segundo rediseño (abajo) | 0.24.0 |
| D | Validación de resoluciones y escalado; después, el instalador (en espera) | 1.0.0 |

### Segundo rediseño (decidido el 2026-11-08, 0.24.0)

Sustituye lo anterior donde choque.

| Tema | Decisión |
|---|---|
| Ventana | Fija de 1024×700 px lógicos, sin redimensionar ni maximizar; se multiplica por la escala de Windows y se reduce si no cabe en la pantalla |
| Estructura | Sin cabecera: logotipo y «Atril» en la navegación; pie con el estado de DeepTutor y Ollama, la operación en curso y la versión. Fondo único `#e9eff8`, sin hueco entre navegación y contenido |
| Navegación | Inicio, Temarios, Biblioteca, Backups, Actividad, Ajustes. Servicios pasa a Inicio; Diagnóstico desaparece (sus herramientas van a Ajustes y el historial a Actividad) |
| Inicio | Estado general con un botón ancho Arrancar/Parar (Arrancar abre Ollama si hace falta y DeepTutor en el navegador; Parar solo DeepTutor). Herramientas: DeepTutor, Ollama, Git, uv, Node.js y el asistente, cada una con logotipo, estado y una sola acción (Instalar, Arrancar, Parar o una marca de instalada) |
| Logotipos | Los oficiales de cada herramienta, con sus colores, en `recursos/marcas` (marcas de sus titulares, solo para identificarlas; ver `MARCAS.txt`). El asistente usa un icono genérico |
| Ollama | Está fuera de la estación: atril solo para el Ollama que abrió (PID y hora de arranque en `data/atril/ollama.json`); uno abierto aparte se muestra en marcha sin botón |
| Temarios | Desplegable con el temario activo, «Nuevo temario» y «Borrar temario». El temario activo es el mismo en Biblioteca y se recuerda en `data/atril/ventana.json` |
| Borrar temario | Definitivo: primera confirmación con lo que se pierde (ficheros, tamaño, KB) y «Abrir carpeta» para guardar lo que interese; la segunda exige escribir el nombre. Se borran primero las KB por la API y la carpeta solo si todas se borran. Sustituye a la papelera |
| Biblioteca | Solo el temario activo (sin columna Temario); sin temarios, tabla desactivada con aviso. «Descargar» y «Actualizar» |
| Ventanas emergentes | Centradas, sin barra de título y con la ventana oscurecida (velo semitransparente en Windows); todos los mensajes las usan |
| Tablas | Margen de 1 em en las cabeceras; las celdas se sangran para alinearse con ellas |
| Textos | Sin comandos ni opciones de la consola; una prueba lo comprueba en todos los módulos salvo `commands/` |
| Ajustes | Todas las claves de `atril.toml` en pestañas (desde 0.33.0: DeepTutor, Atril con actualizaciones, backups e indexado, Avanzado y Herramientas; antes: DeepTutor (asistente, búsqueda), Indexado (Ollama, ritmo), Backups, Avanzado (lo que obliga a reinstalar o reindexar) y Herramientas (instalar o reparar, actualizar, aplicar ajustes, diagnóstico, validar, copiar informe, volver a un commit, registros)). Al guardar se dice qué hace falta (`ops.settings.effects`) y se ofrece aplicarlo |
| Lecturas | Las lecturas de fondo no bloquean botones ni dejan rastro en Actividad; sus errores se muestran en el propio apartado (p. ej., un destino de backups desconectado) |
| Retoques (0.25.0) | Inicio recupera última actividad y último backup. Herramientas de dos en dos y en este orden: DeepTutor y Ollama, Python y uv, Node.js y npm, Git y Asistente; el logotipo abre la web de cada una (con su logotipo oficial, salvo el asistente). El Asistente comprueba el modelo activo en DeepTutor (Claude Code instalado, modelo de Ollama descargado o clave presente en la nube) sin leer la clave. Ajustes con una descripción de una línea por clave, 0,5 em entre claves y Avanzado en una columna desplazable por partes. Sin punto y coma en los textos |
| Tablas ordenables (0.26.0) | Pulsar la cabecera ordena ascendente y, otra vez, descendente, con una flecha de Lucide en la cabecera (Inter no tiene flechas). Los empates, por la primera columna ascendente (alfabética, o por fecha en Backups y Actividad). Se conserva el orden al refrescar |
| Pestañas (0.27.0) | Ajustes usa `widgets.TabBar` en vez de `ttk.Notebook`: pestañas de texto con el estilo de la navegación (azul y subrayado de 3 px, fondo azul claro al pasar) en la cabecera de una sola tarjeta, separadas del contenido por una línea. Sin iconos ni atajos de teclado. «Guardar» se oculta en Herramientas |
| Recuadros de texto (0.27.1) | Fondo de las tablas (`#fafafa`, imagen `campo.png` con borde redondeado: `style.tile(field=True)`), barra de desplazamiento solo si hace falta y selección como las filas de las tablas (`#e7e7e7` y texto `#191919`, por encima del color de nivel) |

### Área de notificación (0.28.0)

| Tema | Decisión | Descartado |
|---|---|---|
| Técnica | `gui/tray.py`: `Shell_NotifyIconW` con `ctypes` (solo stdlib) y una ventana oculta en su propio hilo; las órdenes llegan a Tk por una cola que vacía su sondeo. Fuera de Windows no hay icono | `pystray` (arrastra Pillow), `tk systray` (Tk 9, que Python 3.13 no trae; `tkinter.systray` llega en 3.16) |
| Cerrar la ventana | Con DeepTutor en marcha (lo arrancara quien lo arrancara) se oculta en el área de notificación, también con una operación en curso, que sigue. Sin DeepTutor, atril se cierra del todo, como antes (`model.close_action`) | Preguntar cada vez |
| Salir desde el icono | Para DeepTutor (aunque no lo arrancara atril) y el Ollama que abrió atril (`ops.service.shutdown`). Con una operación en curso, muestra la ventana y pregunta | Dejar DeepTutor en marcha |
| Menú | Mostrar atril (también clic izquierdo), Abrir DeepTutor, Arrancar o parar DeepTutor, Hacer backup, Ver actividad, Salir (`model.tray_menu`) | |
| Notificaciones | Con la ventana oculta: aviso la primera vez, el final de cada operación y si DeepTutor se para sin una operación de atril. Los errores van a la notificación, no a una ventana | |
| Instancia única | Abrir atril otra vez muestra la ventana existente (busca la ventana oculta `AtrilTrayWindow`) | |
| Arranque con Windows | No | |
| Nombre en Windows | La configuración de la barra de tareas muestra «Python» (la descripción de `pythonw.exe`, que es el proceso del icono). Se resolverá con un lanzador propio en el instalador | Cambiarlo desde el código (el icono no lleva nombre) |

### Parches al arrancar (0.28.1)

`arrancar` aplica los parches pendientes (código original intacto) antes de lanzar DeepTutor, que está parado. Antes solo avisaba, y unos parches deshechos (actualización interrumpida) volvían a abrir la consola en cada arranque. Un parche con el código cambiado sigue siendo un error y no se fuerza.

### Ajustes (0.33.0)

Pestañas: DeepTutor, Atril, Avanzado y Herramientas. Atril reúne, en una columna desplazable, Actualizaciones, Backups e Indexado (al final, con la casilla de Ollama al principio de su parte), en lugar de tres pestañas cortas.

### Instalador (0.29.0)

| Tema | Decisión | Descartado |
|---|---|---|
| Construcción | Job `installer` de `publish.yml` en `windows-latest`, tras publicar en PyPI: Inno Setup (`choco`), `uv.exe` de versión fija con su SHA-256, prueba de instalación y desinstalación silenciosas y `atril-X.Y.Z-setup.exe` adjunto a la release. A mano (`workflow_dispatch`) rehace el de la versión publicada | Construirlo en cada PR (necesita la versión en PyPI) |
| Contenido | `instalador/atril.iss`: `uv.exe`, icono y licencia. Al instalar, `uv tool install atril==X.Y.Z` con Python 3.13 propio, todo dentro de `%LOCALAPPDATA%\Programs\Atril` (`bin`, `herramientas`, `python`; sin caché). Salida en `instalacion.log` | Usar las carpetas por defecto de uv (se mezclaría con un `uv tool install atril` del usuario) |
| Accesos y CLI | Acceso en el menú Inicio (y en el escritorio, opcional) con `AppUserModelID` `atril.gui`, el de la ventana. `bin` se añade al final del PATH del usuario y se quita al desinstalar | |
| RedirectionGuard | Inno Setup lo activa y sus procesos hijos lo heredan: uv no puede recorrer el enlace de versión menor de Python (os error 448 en Windows 11). Se desactiva (`RedirectionGuard=no`): Setup corre como el propio usuario, sin elevar, y no hay frontera de privilegios que proteger | `ExecAsOriginalUser` (sin elevación, el hijo seguía con la mitigación) |
| Una carpeta por versión (0.34.0) | `UV_TOOL_DIR` = `herramientas\<versión>`: actualizar no borra el entorno en uso (tras cerrar la ventana, el antivirus aún retenía `_psutil_windows.pyd` y uv fallaba con «Acceso denegado» incluso esperando al proceso). Los entornos de otras versiones se borran después (`RemoveOldTools`), y lo que siga retenido, en la siguiente | Borrar y reinstalar en el sitio (`uv tool install --force` sobre el mismo entorno) |
| Atril abierto | La ventana crea el mutex `AtrilGui` (`tray.hold_mutex`): instalar o desinstalar pide cerrarla antes (`AppMutex`) | |
| Firma | Sin firmar por ahora (SmartScreen avisa). Después, solicitar SignPath Foundation | Azure Trusted Signing (de pago) |
| Nombre «Atril» en el área de notificación | Pendiente: lanzador `Atril.exe` que cargue Python en su propio proceso | |

## Lecciones de la instalación previa

- Backup: se retiran restic, rclone y los git bundles. Las KB ocupan varios GB y rclone exigía una configuración compleja; ahora son ficheros `atril-<fecha>.zip` (deflate 9) o `.tar.xz` (xz 9) en carpetas (disco externo o Google Drive para escritorio), verificados y con `conservar` copias por destino. Se retiran también `scripts/backup.py` y `scripts/migrar_estacion.py` (la migración ya está hecha).

- Una sola estación por equipo, en la variable de usuario `ATRIL_ESTACION` (registro del usuario; desde 0.17.0 sin `setx`). Sin `--estacion` ni fichero en `%APPDATA%`. La primera ejecución ofrece la carpeta actual si tiene `atril.toml`, si no pregunta la ruta y, si allí no hay `atril.toml`, ofrece inicializarla.

- El indexado puede dejar el equipo sin respuesta: el CLI de DT corre con prioridad baja de CPU y disco (no cambia el resultado), `[indexado] hilos` limita los hilos de PyTorch/Docling, y se avisa si el embedding no cabe entero en la VRAM (la parte en CPU satura el procesador). Con la GPU al 100 %, `lote_embedding` y `pausa_embedding` (perfil de embedding de DT: `batch_size`/`batch_delay`) dejan huecos para el escritorio.

- Windows: `deeptutor start --detach` con `DETACHED_PROCESS` abre una consola vacía (el `python.exe` del venv es un redirector); parche `arranque-sin-ventana` (`CREATE_NO_WINDOW`).

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

## Web (0.35.0)

| Tema | Decisión | Descartado |
|---|---|---|
| Sitio | Zensical (`zensical.toml`, `docs/`, `docs_templates/`), con la estructura de pyMedia, publicado en GitHub Pages por `docs.yml`: https://isidro-rodriguez.github.io/atril/ | Seguir con `docs/*.md` sueltos |
| Tema | La paleta de la ventana (`style.py`): fondo `#e9eff8`, contenido en tarjeta blanca redondeada, acento `#0f5ec9`, Inter; modo oscuro con la misma idea | |
| Contenido | Portada y Guía para alumnos sin conocimientos técnicos; Documentación avanzada (conceptos, CLI, `atril.toml` y `temario.toml` con los ejemplos incluidos por `--8<--`, indexado, copias, instalador); Desarrollo | |
| Capturas | Generadas con la ventana real y una estación de ejemplo: alumna de 2.º de Bachillerato de Ciencias, un temario por asignatura (Física, el que más fuentes tiene, como activo) | Capturas a mano |
| Documentos retirados de `docs/` | `esquemas.md` pasa a las páginas de configuración; `ejemplos/` a `docs/documentacion/ejemplos/`; este fichero, a `DECISIONES.md` en la raíz | |

## Revisión de GPT (0.36.0)

| Tema | Decisión | Descartado |
|---|---|---|
| Capturas | `scripts/capturas.py` en tres pasos (estación de ejemplo con fechas fijas, ventana real con servicios simulados, captura). Las genera `docs.yml` en `windows-latest` con el código del mismo commit, con rutas de Windows de ejemplo (`D:\Estudio`, `D:\Copias\Atril`); no se versionan. Falla si falta una o si la versión no es la de `pyproject.toml` | Capturas versionadas (se quedaban en una versión anterior) |
| Inicio | Tarjeta blanca «Estado general» dominante: icono y palabra grandes, una frase de una línea (recortada con «…») y los botones Abrir en el navegador y Arrancar/Parar abajo a la derecha. Sin último backup ni última actividad. Herramientas compactas, de dos en dos | Tarjetas de último backup y actividad, resumen en la cabecera |
| Enlaces | Iconos de la web, GitHub y PyPI al pie de la barra lateral | |
| Temarios | Columnas Fuentes, Indexadas, Por indexar (nuevas o cambiadas) y Sin fichero (`model.kb_counts`); las retiradas no cuentan como fuentes | Una sola columna «Faltan» que mezclaba ambas |
| Verificaciones | `data/atril/verificaciones.json` guarda el resultado de cada comprobación con el tamaño y la fecha de modificación de la copia: deja de valer si la copia cambia. Estados Verificada, Con errores y Sin comprobar | Solo en memoria (se perdía al cerrar) |
| Actividad | El detalle muestra el resultado completo. Si no se puede guardar, el pie lo avisa una vez y el error va a `atril-diagnostico.log` en la carpeta temporal | Ignorar el error |
| Ventana | Sigue fija de 1024×700 | Redimensionable |

## Inicio (0.37.0)

| Tema | Decisión | Descartado |
|---|---|---|
| Estado general | Icono (104 px) y estado (52 pt) con una frase de una línea, botones apilados a la derecha y, tras una línea, tres datos clicables: temarios, fuentes y último backup (antigua a los 7 días) | Último backup y actividad como tarjetas aparte |
| Frases | Cortas y concretas: «Falta herramienta por instalar.», «Parche pendiente.», «Parche no encaja con DeepTutor.», «Inicia DeepTutor para estudiar.». El titular de error es «Atención» (cabe a 52 pt) | Listar las herramientas que faltan (ya se ven en sus baldosas) |
| Botón principal | Resuelve el estado (`model.primary`): instalar, revisar en Ajustes y aplicar parche (naranja del logotipo, texto marino), arrancar o parar | Arrancar con un parche pendiente o que no encaja |
| Herramientas que faltan | Se exigen todas (Git y uv hacen falta para actualizar): Arrancar queda desactivado (`App.block`, que sobrevive a otras operaciones) y el área de notificación avisa | Dejar arrancar si solo faltan Git o uv |
| Capturas | Física con cuatro KB (teoría, problemas, divulgación y normativa) y la Biblioteca ordenada por base | Una sola KB por temario |
| Datos de Inicio | Formato corto («8 · Física», «52 · 1 sin fichero») recortado con «…» a 2 em del divisor, según el ancho real de cada columna (0.37.1) | Textos completos («8 temarios · activo: Física») |
| Reapertura tras actualizar | El instalador abre la ventana en `DeinitializeSetup` con `--tras-instalar`, que espera a que desaparezca el mutex `AtrilSetup`; sin él, la ventana no se abre durante una instalación. Sin gestor de reinicio (0.37.1) | `[Run]` con `Check` (se ejecuta antes de que uv instale: abría la versión anterior) |

## Publicación de la web (0.37.2)

| Tema | Decisión | Descartado |
|---|---|---|
| Cuándo | Solo con cada versión: `publish.yml` llama a `docs.yml` con el tag nuevo y todo se construye con el código de ese tag. A mano, solo se rehace un tag ya publicado | Publicar con cada push a `main` o en las pull requests |
| Script de capturas | Parte de la publicación, sin modo manual. Estación en `D:\Estudio` (aislado por el runner: falla si existe, se borra al final) o en una carpeta temporal fuera de la CI | Marcas de propiedad en carpetas fijas |
| Errores | Sin `mainloop`: el script procesa los eventos de Tk mientras espera, recoge los errores de callbacks y del trabajo en segundo plano y sale con código distinto de cero | Errores que se quedaban en un callback |
| Sincronización | Cada apartado espera a mostrar sus datos y a que no haya trabajo ni eventos pendientes durante varias vueltas, con 60 s como máximo | Esperas fijas |
| Validación | Las seis capturas, PNG de 1024×700 y un mínimo de 20 KB, en una carpeta temporal antes de sustituir las de salida | Dar por buena una generación incompleta |
| GDI | `argtypes`/`restype` de cada función, cada resultado comprobado, bitmap deseleccionado antes de leerlo y borrarlo, y liberación en `finally` | |
| Biblioteca | Doble clic en una fila abre su documento (`model.document_path` + `desktop.open_path`); sin documento en disco, un aviso (0.38.0) | |
