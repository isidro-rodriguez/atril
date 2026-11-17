# AGENTS.md

Instructions for AI agents working on **atril**: ventana y CLI para gestionar una instalación local de DeepTutor y sus temarios.

The shared sections below are the same in every project. Project-specific rules are at the
end, under **Project rules**, and take precedence when they differ.

<!-- shared:start — managed by assistant-skills/new-python-project (scaffold.py sync). Edit there, not here. -->
## Shared rules

**Language.** Code and identifiers in English. Docstrings, comments, README, `docs/`,
CHANGELOG, commits and user-facing messages in Spanish. This file stays in English.

**Tools.** `uv` only, never `pip install`; run everything from the project root.
Quality gate: `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`,
`uv run pytest`. The same gate as `poe check`, if Poe the Poet is installed globally; poe is
never a project dependency, and everything must also work with plain `uv run`.

**Workflow.**

1. Read `README.md`, `pyproject.toml`, this file and the related tests before changing code.
2. Make the smallest change that solves the task: no unrelated refactors, no formatting of
   untouched files, no new dependency without a reason (prefer the standard library).
3. Don't change CI, tool configuration or project structure unless the task needs it.
4. Don't run a failing command more than twice: stop, give the root cause and the exact error,
   propose the minimal fix and ask.
5. Don't run state-changing git commands (commit, push, tag, reset, rebase) unless the user
   asks or the commit policy in **Project rules** allows it. Never `--no-verify`.
6. Leave no secrets, temporary files or TODOs without context. Never hand-edit `uv.lock`.

**Code.** Strict type hints on every signature. Google-style docstrings: complete for public
identifiers, one line for private ones; a public docstring's `Raises` also lists the
exceptions raised by the private functions it calls. Comments explain the *why*. Prefer
simple, explicit code; `pathlib` over `os.path`. Ruff and ty enforce the rest; don't fight
them with ignores.

**Tests.** `pytest` in `tests/`. Cover relevant logic and every fixed bug; they must pass on
Linux and Windows.

**Commits.** Conventional Commits in Spanish (`feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `chore:`), one intent per commit, explaining the *why*.

**Releases.** Only for versioned projects (a real version and `CHANGELOG.md`). Before
pushing changes to the package, use the `python-release` skill. Without it: SemVer bump,
`## [Unreleased]` → `## [X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md`, `uv lock`, then
`chore: bump versión a X.Y.Z`. Never tag without confirmation.

**Done** when the quality gate and any extra gate in **Project rules** pass, and the README
and docs reflect any change in usage.

Project rules below take precedence over these. Shared rules change in assistant-skills
(`scaffold.py sync`), not by hand here.
<!-- shared:end -->

## Project rules

atril is a window (`atril-gui`, tkinter) and CLI (`atril`, Typer) that manages a local
[DeepTutor](https://github.com/HKUDS/DeepTutor) installation and its syllabi: sources,
knowledge bases, evaluation and backup. Target platform: Windows; the CLI also runs on Linux
and macOS.

### Language

CLI commands, options and configuration keys are **in Spanish** (`atril kb indexar`,
`--detalle`, `[[fuente]]`): they are user-facing. Map them to English identifiers in code
(`[[fuente]]` → `Source`, `temario` → `Syllabus`, `estación` → `Station`).

### Structure

```bash
.
├── .github/                # CI (ci.yaml), PyPI publishing (publish.yml), website (docs.yml)
│                           #   and Dependabot
├── .pre-commit-config.yaml # pre-commit/pre-push hooks (ruff, ty, pytest)
├── AGENTS.md               # This file (CLAUDE.md imports it)
├── CHANGELOG.md            # Keep a Changelog
├── conftest.py             # Root pytest config: skips GUI doctests without tkinter
├── LICENSE                 # MIT
├── pyproject.toml          # Project: deps, build, tools (ruff, ty, pytest, uv, poe)
├── README.md               # Minimal project overview
├── uv.lock                 # Lockfile, tracked by git
├── instalador/atril.iss    # Windows installer (Inno Setup), built by publish.yml
├── scripts/capturas.py     # Website captures from the real window (run by docs.yml on Windows)
├── scripts/recursos/       # Dev-only generator of gui/recursos (logo SVG, tool logos in
│                           #   marcas/, icons, fonts, card)
├── DECISIONES.md           # Design decisions (source of truth for scope and phases)
├── zensical.toml           # Website (Zensical), published to GitHub Pages by docs.yml
├── docs_templates/         # Website template overrides (favicons, manifest)
├── docs/                   # Website sources: index, guia/ (students), documentacion/
│   │                       #   (advanced), desarrollo/; assets/ (atril.css theme, captures)
│   └── documentacion/ejemplos/  # Example atril.toml/temario.toml, validated by the tests
├── src/atril/
│   ├── commands/           # CLI commands (config, deeptutor, install, syllabus, knowledge, backup,
│   │                       #   gui)
│   ├── ops/                # Use cases shared by CLI and GUI (service, backup, station, syllabus,
│   │                       #   sources, knowledge, installation, settings, updates)
│   ├── gui/                # tkinter + sv-ttk GUI (`atril-gui`): app (shell), widgets, style,
│   │                       #   model, activity, worker, dialogs, desktop, tray and one module per
│   │                       #   section (home, syllabi, library, backups, history,
│   │                       #   settings); recursos/ (logo, tool logos, Lucide icons, Inter)
│   ├── config/             # TOML schemas: station.py (atril.toml), syllabus.py (temario.toml)
│   ├── backup.py           # zip/tar.xz backups, verify, prune, extract and swap
│   ├── checks.py           # Finding/Level: results shown by commands
│   ├── deeptutor.py        # DeepTutor control (CLI, health URLs, orphans)
│   ├── errors.py           # AtrilError (Spanish message + optional log), CancelledError
│   ├── evaluation.py       # Full-text retrieval evaluation (app/ Python) and reports
│   ├── install.py          # Install/update steps (git, uv, npm, ollama, deeptutor config)
│   ├── lock.py             # Station lock (<root>/.atril.lock) for long operations
│   ├── knowledge.py        # KB indexing: plan, ledger, CLI adds, run state, reindex API
│   ├── net.py              # Minimal urllib helpers (is_up, get_json)
│   ├── ollama.py           # Ollama status and checks
│   ├── patches.py          # Patch registry and idempotent apply
│   ├── processes.py        # Port owners and process trees (psutil)
│   ├── sources.py          # Source download, registry, version check and history
│   ├── __init__.py         # Exposes __version__ via importlib.metadata
│   ├── __main__.py         # python -m atril
│   ├── main.py             # Typer app: registers commands (entry point `atril`)
│   └── py.typed
└── tests/
```

- Every `__init__.py` must include a short docstring describing the module or package.
- The project uses `uv` as dependency manager and build backend.
- Runtime dependencies: `acodo` (`acodo>=0.5.1,<1`), `typer` with `rich` (CLI output),
  `psutil` (ports, command lines and process trees, portable and testable on Linux CI),
  `tomlkit` (edits `temario.toml` keeping comments; `tomllib` only reads) and `sv-ttk` (Windows 11
  look for the tkinter GUI). Anything else needs a justification (stdlib first). Raise the `acodo`
  lower bound only when a newer API is needed.
- `README.md` must stay minimal: what it is, installation, usage, quality commands and links.

### Domain rules (load-bearing)

Read `DECISIONES.md` before any non-trivial change. Key points:

- **DeepTutor never enters atril's `uv.lock`.** Control it through its CLI
  (`app/.venv/Scripts/deeptutor.exe`) and its API (`localhost:8001`) via `subprocess` and
  `urllib`. Only exception: full-text evaluation runs with `app/`'s Python.
- **One station per computer**, stored in the user variable `ATRIL_ESTACION` (written to
  `HKCU\Environment` with `winreg` on Windows, no `setx`; read from the registry if the current
  environment lacks it). No `--estacion` option and no config file of atril's own; the first
  run picks, or initializes, the station.
- **The station layout is fixed**: `<root>/atril.toml`, `app/`, `data/`, `temarios/<id>/`.
  `DEEPTUTOR_HOME` (`deeptutor --home`) is the station root; DeepTutor creates `data/` inside.
  Derive paths from `Station` / `Syllabus` properties, never hardcode them elsewhere.
- **atril's code never lives inside the station.**
- Target platform is Windows (PowerShell 7). CI also runs on Linux: keep logic
  platform-neutral and isolate Windows-only calls so tests can run anywhere.
- Never store secrets in config.
- `[ollama]` is optional: without it DeepTutor runs (cloud LLM) but nothing is indexed. Read it
  through `Station.require_ollama()` wherever embeddings are needed.
- `temario.toml` is written only by `ops.syllabus` with `tomlkit`: validate the new text with
  `load_syllabus` in a temporary copy, then replace through `.nuevo`.
- Configuration errors raise `atril.config.ConfigError` with a Spanish message naming the file,
  table and key. Commands catch it, print it in red and exit with code 1.
- Every schema change updates `docs/documentacion/atril-toml.md` or `temario-toml.md`,
  `docs/documentacion/ejemplos/` and the tests. Website: Spanish, friendly in `index.md` and
  `guia/`, technical in `documentacion/`; GUI captures come from the real window with a
  sample station: `scripts/capturas.py` (fixed dates, faked services, Windows example paths)
  generates them in `docs.yml` on `windows-latest`; they are gitignored, never committed
  (`uv run zensical build` must pass). The site is published per release only: `publish.yml`
  calls `docs.yml` (`workflow_call`) with the new tag and both jobs check out that tag. The
  script is part of that pipeline, not a manual tool: it waits for each view to load (timeout),
  turns any Tk or worker error into a non-zero exit, frees GDI objects in order and validates
  every PNG before replacing the output folder. Keep it in sync with the GUI and CLI.
- **CLI output uses Rich**, never `print`/`typer.echo`: the shared `console`/`err_console` from
  `commands._common`, `show()` for findings, `success()`/`fail()`, `console.status()` spinners for
  waits, `rich.table.Table` for listings and `Panel` for log excerpts. Always `escape()` external
  text (paths, config messages with `[[fuente]]`, command lines). Commands are grouped with
  `rich_help_panel` and help strings may use Rich markup.
- **Use cases live in `atril.ops`** and never import Rich or Typer: they return results or
  `Finding`s, report progress to an `ops.Reporter` (`show`, `busy`, `progress`) and raise
  `atril.errors.AtrilError` (every module error derives from it). Confirmations are asked by the
  interface before calling them. `commands/` only parses options, prints (`ConsoleReporter`,
  `fail_error`) and sets the exit code; the GUI does the same with widgets. `Reporter.busy`
  yields an `update(text)` callable for long waits (indexing minutes and phase, download size).
  Cancellation is a `threading.Event` checked at safe points: between sources, or in the indexing
  tick (it kills DeepTutor's process, like Ctrl+C, and the next run continues from that source).
- **GUI** (`atril.gui`): never blocks Tk's thread; every operation goes through `gui.worker.Worker`
  (one job at a time, events through a queue drained with `after`). Texts and backgrounds use
  `tk` widgets via `style.label`/`style.card` (sv-ttk's `tk_setPalette` overrides `ttk.Label`
  colors); `style.apply` processes `<<ThemeChanged>>` before building widgets. Buttons, bars and
  scrollbars stay `ttk`. Every `ttk.Style.configure` queues another `<<ThemeChanged>>`, so
  configure styles only in `style.apply` (it flushes them). Use the named fonts and colors of
  `style`, Lucide icons via `style.icon` (pre-rendered PNGs; regenerate with
  `scripts/recursos/generar.py`, never hand-edit) and never rely on color alone (level icons).
  Glyphs must exist in Inter's latin subset (no ✓, ✗ or arrows). View logic without Tk lives in
  `gui/model.py` and `gui/activity.py` so it is tested without a display; window tests skip when
  there is none. Each operation is an activity `Event` saved in `data/atril/actividad.jsonl`;
  a failed save warns once in the footer and goes to `atril-diagnostico.log` (temp folder).
  Backup checks persist in `data/atril/verificaciones.json`, valid while size and mtime match.
  Operations whose effect is not visible (Ajustes > Herramientas) pass `report=True` to
  `App.run`: a `Modal` with `activity.report_text` on success (failures always get one).
  Inicio's main button resolves the shown state (`model.primary`); `App.block` keeps an action
  button disabled across operations (start while a tool is missing). `style.WARNING_BUTTON` is
  the logo's orange with navy text, for warnings only.
- Every box has rounded corners: `style.card` (on the page) and `style.tile` / `Tile.Atril.TFrame`
  (inside a card; `field=True` for text boxes, with the tables' `#fafafa`). No `ttk.Notebook`: tabs are `widgets.TabBar` (navigation style) on a card.
- GUI layout: fixed 1024x700 window (logical px, scaled with Windows and reduced if the screen is
  smaller), not resizable; no header; sidebar with logo and name; footer with service status,
  current operation and version. Every message or question is a `gui.dialogs.Modal` (centered,
  no title bar, veil over the window on Windows); `messagebox` only before the window exists
  (first run). Never name widget attributes like tkinter internals (`_name`, `_root`, `_w`).
- GUI texts never mention CLI commands or options (`tests/test_textos.py` scans every module
  except `commands/`): shared `ops` messages say what to do, the CLI adds its own hint. GUI
  texts never use ";" and setting descriptions fit in one line.
- Tables are sortable with `widgets.TableSorter`: views register per-row sort keys (dates as
  ISO or stamps, numbers as ints, text through `model.fold`) and call `apply()` after
  refilling; ties sort by the first column ascending (`model.sort_order`).
- Inicio's assistant card reads the active chat model from DeepTutor's `model_catalog.json`
  (`deeptutor.active_assistant`) and only reports whether a key exists: never read the key
  into anything else, never show or log it.
- GUI performance (it is a launcher; it must feel instant): switching sections never waits.
  `App.show_view` reloads a view only the first time, after an operation, or past
  `STATUS_TTL` for Inicio; hidden views are `grid_remove`d. Quiet reads (`run(quiet=True)`) do
  not block buttons nor leave activity events; their errors go to `on_error`. Keep `ttk` image
  elements large (it tiles them) and keep references to named fonts. Never hash or scan files on the Tk
  thread; `knowledge.file_digest` caches big files. Local HTTP goes through `net.local_url`
  (fast port probe: Windows takes ~2 s per refused loopback address).
- Deleting a syllabus from the GUI is permanent, after two confirmations (the first lists what is
  lost and offers to open the folder; the second requires typing its name): `ops.syllabus.delete`
  deletes its KBs through the API first and the folder only if all succeed. Ajustes edits every
  key in `ops.settings.EDITABLE` (all of `atril.toml`); delicate ones live in the Avanzado tab,
  and `ops.settings.effects` says what a change needs (apply, reinstall, reindex).
- Ollama lives outside the station: atril only stops the Ollama it started, identified by PID and
  start time in `data/atril/ollama.json` (`ops.service.ollama_owner`).
- Long operations (backup, restore, install, update, `kb indexar`/`reindexar`) hold the station
  lock (`lock.station_lock`, taken inside `ops`): an OS lock (`msvcrt`/`fcntl`) on `.atril.lock`,
  released by the OS if the process dies, reentrant within a process. Never delete the lock file.
- Closing the GUI never kills an operation: it asks the job to cancel at a safe point (or waits
  for it) and destroys the window only when the worker is done.
- Tray (`gui/tray.py`, Windows only, `ctypes` + `Shell_NotifyIconW`, no dependency): closing the
  window with DeepTutor running hides it to the tray (`model.close_action`); without DeepTutor it
  quits as before. The tray's "Salir" stops DeepTutor and atril's own Ollama
  (`ops.service.shutdown`). Tray clicks reach Tk only through `Tray.commands`, drained in
  `App._poll`; never touch Tk from the tray thread. A second `atril-gui` shows the running one.
- Windows installer (`instalador/atril.iss`, job `installer` in `publish.yml`): per user, ships
  a pinned `uv.exe` (update `UV_VERSION`/`UV_SHA256` together) and runs `uv tool install
  atril==X.Y.Z` with every uv folder inside the program folder (one tool dir per version,
  `herramientas\<version>`, so an update never deletes the venv in use; old ones are removed after); uninstalling deletes only that
  folder and its PATH entry, never the station. The GUI holds the `AtrilGui` mutex (`AppMutex`).
  Setup holds `AtrilSetup` (`SetupMutex`): the GUI does not open while it exists, and setup
  reopens it only in `DeinitializeSetup` (never from `[Run]`, processed before uv installs)
  with `--tras-instalar`, which waits for that mutex. No Restart Manager
  (`CloseApplications=no`).
- Self-update (`ops.updates`): the GUI checks GitHub's latest release at startup (quiet, unless
  `[atril] buscar_actualizaciones = false`). Only an installer install (`installer_folder`) is
  updated in place: download, verify the release's SHA-256 `digest`, `tray.release_mutex()`,
  launch the installer with `/SILENT /abrir=si /esperar=<pid>` (it waits for that process: the
  venv files are in use until it exits) and quit; any other install only links the
  release page. The CLI only warns, in `atril estado` (same key). Tests run offline: `tests/conftest.py`
  makes `net.open_url` raise unless a test replaces it.
- Every `subprocess` call passes `creationflags=processes.no_window()`: without a console (GUI,
  `pythonw`) Windows would open an empty console window per child.
- Commands report through `atril.checks.Finding` (ok/info/aviso/error) and `commands._common.show`;
  a command exits with code 1 when any finding is an error.
- Only kill processes with an **argument that is a path inside the station root**, compared as
  normalized paths (`processes._normalize`, which resolves `.`/`..`), never as substrings: `D:\DeepTutorBackup` is not inside
  `D:\DeepTutor`. Never touch other processes.
- Patches are idempotent text replacements registered in `atril.patches.PATCHES`. Only two states
  are clean: original once and patched absent (pending), or the reverse (applied); a patch with
  an `upstream` marker is also clean when neither text is there but the marker is (DeepTutor
  ships the fix: `UPSTREAM`, nothing to do). Anything else means DeepTutor changed and is an
  error, never forced.
- Tests never wait for real time or call real services: fake `time.sleep`/`time.monotonic`,
  `ollama.get_status`, `DeepTutor` methods and `install.run_command`/`install.capture`.
- `deeptutor doctor` does not accept `--home`; pass it explicitly only to `init`, `config`,
  `start` and `stop`, and rely on `DEEPTUTOR_HOME` (from `DeepTutor.env()`) for the rest.
- DeepTutor settings come from `atril.toml` (no `setup.json`): `config apply` for LLM, embedding,
  search and ports; `install._SETTINGS_SCRIPT`, run with `app/`'s Python, for parser, chunks and
  embedding pace (`batch_size`/`batch_delay` of the active embedding profile, which `config apply`
  rewrites); `kb indexar` reapplies it before indexing.
- `app/` is a shallow clone: update with `fetch --depth 1` + `reset --hard FETCH_HEAD`, only on a
  clean tree (files differing only in line endings, from older CRLF patch writes, do not count), after reverting patches and after checking that `origin` and the current branch match
  `atril.toml` (abort otherwise). `actualizar --commit <full sha>` goes to that commit instead
  (rollback; GitHub serves reachable SHAs to shallow fetches). `actualizar` reapplies `config apply`, parser/chunks and `doctor`;
  a venv with another Python version is recreated (`uv venv --clear`).
- State files (`registro.json`, `indexado.json`) are `{"version": 1, "<section>": {...}}` with
  exact fields and types (`_toml.load_state` / `check_record`); anything else raises
  `StateFileError` and is never overwritten nor read as empty.
- Sources keep a **stable file name** (`archivo` or the URL's last segment, no date): versions go
  to `fuentes/historico/`, and `fuentes/registro.json` (text, sorted) records hash and dates.
  Downloads write `.part`/`.nuevo` first and require the `%PDF-` header; a failed download never
  replaces the current file. All HTTP goes through `net.open_url` (browser-like User-Agent), which
  tests replace.
- KB indexing: new sources are added **one by one** with the DeepTutor CLI (`kb create|add`, no
  server needed), started at below-normal CPU/IO priority (`processes.lower_priority`) and with
  `[indexado] hilos` as thread limit; `fuentes/indexado.json` records the indexed hash per KB and
  source. DeepTutor stores a changed file with the same name as `name (2).pdf` and never purges vectors, so changed
  and removed sources are handled only in `kb reindexar`: delete the old file through the API,
  re-add, then `POST /reindex` with the active `embedding_model` and follow the run of the task
  it returns (the adds leave their own completed runs); if DeepTutor was stopped, stop it after. Success of an add is a **new**
  completed run (different `task_id`) or DeepTutor's "already indexed" message, never a lookup by
  file name. Run state comes from `<kb>/.indexing-run.json`; a `running` run whose owner process
  died counts as `interrupted`, and those states require restarting DeepTutor before reindexing.
- Evaluation runs DeepTutor's evaluator with `app/`'s Python (`evaluation._EVAL_SCRIPT`), matching
  gold answers against `evidence_text` (full chunk) instead of the 200-char `content`. Reports go to
  `temarios/<t>/eval/informes/` — never inside `espacio/`, which the agent reads — and each run is
  compared with the latest previous report for the same KB, dataset and `k`.
- Backups are compressed archives (`zip` deflate 9 or `tar.xz` xz 9), written with the stdlib to
  the folders in `[backup] destinos` (no restic, rclone or git bundles). Each one holds
  `atril.toml`, `data/` (without `data/atril/logs/`) and `temarios/` — never `app/` — plus
  `atril-backup.json` (validated strictly by `backup.parse_manifest`: station root, date, version,
  blanked keys, `completa` and the file inventory with sizes; manifests without inventory are
  legacy and accepted). DeepTutor is stopped first (SQLite) and restarted after. Symlinks and
  junctions are skipped. The archive is written as `.part`, renamed without overwriting
  (`-2`...), verified (zip CRC / full xz stream and the inventory) and then copied to and verified
  in the other destinations. An archive with unreadable files is named `…-incompleta`: excluded
  from `archives()`, retention and restore. Secret values in `data/user/settings/model_catalog.json` are
  blanked in the archive (`backup.redact_secrets`; the original is untouched) and restore warns to
  re-enter them. Only `atril-*` files are pruned to `conservar`, and nothing is
  pruned if a file could not be read or a copy failed (exit code 1). A destination whose parent
  folder is missing is a disconnected disk and is skipped with a warning. Restore extracts to
  `<root>.restaurar-<ts>` (rejecting absolute or `..` paths), then swaps in; the current content
  moves to `<root>.previo-<ts>` and is never deleted. DeepTutor must be stopped, checked again
  inside `restore()` right before the swap. A failed swap is rolled back; if the rollback is
  incomplete (`SwapError.uncertain`) nothing is deleted, not even the staging folder. An archive
  from another root requires `--nueva-ruta`.

### Extra quality gates

- Before any non-trivial change, read `DECISIONES.md` as well as the files listed in the shared
  workflow.
- Website: `uv run zensical build` must pass (`poe serve` for a local preview).

### Commit policy

Never commit automatically: report the result and wait for confirmation.

### Publishing

`publish.yml` publishes to PyPI (trusted publishing, no token) on every push to `main` that
touches `src/`, `pyproject.toml`, `README.md` or `LICENSE`, unless the tag `vX.Y.Z` of the
current version already exists; it then creates that tag and a GitHub release. So a push that
changes the package **must** bump the version, or nothing is published. `README.md` is the PyPI
page: use absolute GitHub URLs for links.

Before each release, also review `README.md` (the PyPI page): commands, options, the GUI
description and installation steps must match the release; update it in the same release if
anything changed.

<!-- zensical:start (managed by the zensical-site skill; edit there, not here) -->
### Documentation site (Zensical)

- Layout: `zensical.toml`; `docs/` (sources, `docs/site.webmanifest`, `docs/assets/{favicon,fonts,images,stylesheets}`); `docs_templates/` (`main.html`: favicons, manifest and `[project.extra] theme_color`; `python/material/languages/es.html.jinja` when mkdocstrings is used). Only `uv run zensical build` writes `site/` (gitignored).
- Template paths are relative (`{{ 'assets/…' | url }}`, never a leading `/`) so the site works under a sub-path such as GitHub Pages.
- Gate: `uv run zensical build` must end with "No issues found"; after changing the layout, run the skill's `site.py check`.
- Upgrading Zensical: use the skill's `site.py upgrade`, which diffs every template in `docs_templates/` against the new theme before the lock changes land.
<!-- zensical:end -->
