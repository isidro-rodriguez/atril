# CLAUDE.md

## Language

- **Code and identifiers in English**: variables, functions, constants, classes, methods,
  parameters, modules, and tests.
- **Documentation in Spanish**: docstrings, comments, error messages, README, docs, and commits.
- User-facing error messages must be in Spanish. Exception names and internal identifiers must
  be in English.
- **CLI commands, options, and configuration keys are in Spanish** (`atril kb indexar`,
  `--detalle`, `[[fuente]]`): they are user-facing. Map them to English identifiers in code
  (`[[fuente]]` → `Source`, `temario` → `Syllabus`, `estación` → `Station`).
- This file, `CLAUDE.md`, is written in English so the agent does not need to translate
  instructions.

## Expected structure

```bash
.
├── .github/                # CI (ci.yaml), PyPI publishing (publish.yml) and Dependabot
├── .local/                 # Private local files (backups), not tracked by git
├── .pre-commit-config.yaml # pre-commit/pre-push hooks (ruff, ty, pytest)
├── CLAUDE.md               # This file
├── CHANGELOG.md            # Keep a Changelog
├── conftest.py             # Root pytest config: skips GUI doctests without tkinter
├── LICENSE                 # MIT
├── pyproject.toml          # Project: deps, build, tools (ruff, ty, pytest, uv, poe)
├── README.md               # Minimal project overview
├── uv.lock                 # Lockfile, tracked by git
├── scripts/recursos/       # Dev-only generator of gui/recursos (logo SVG, tool logos in
│                           #   marcas/, icons, fonts, card)
├── docs/
│   ├── decisiones.md       # Design decisions (source of truth for scope and phases)
│   ├── esquemas.md         # atril.toml and temario.toml reference
│   └── ejemplos/           # Example config files, validated by the tests
├── src/atril/
│   ├── commands/           # CLI commands (config, deeptutor, install, syllabus, knowledge, backup)
│   ├── ops/                # Use cases shared by CLI and GUI (service, backup, station, syllabus,
│   │                       #   sources, knowledge, installation)
│   ├── gui/                # tkinter + sv-ttk GUI (`atril-gui`): app (shell), widgets, style,
│   │                       #   model, activity, worker, dialogs, desktop and one module per
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
  Put any extra explanation in this file instead.

## atril rules (load-bearing)

Read `docs/decisiones.md` before any non-trivial change. Key points:

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
- Every schema change updates `docs/esquemas.md`, `docs/ejemplos/` and the tests.
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
  there is none. Each operation is an activity `Event` saved in `data/atril/actividad.jsonl`.
- Every box has rounded corners: `style.card` (on the page) and `style.tile` / `Tile.Atril.TFrame`
  (inside a card). No `ttk.Notebook`: tabs are `widgets.TabBar` (navigation style) on a card.
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
- Every `subprocess` call passes `creationflags=processes.no_window()`: without a console (GUI,
  `pythonw`) Windows would open an empty console window per child.
- Commands report through `atril.checks.Finding` (ok/info/aviso/error) and `commands._common.show`;
  a command exits with code 1 when any finding is an error.
- Only kill processes with an **argument that is a path inside the station root**, compared as
  normalized paths (`processes._normalize`, which resolves `.`/`..`), never as substrings: `D:\DeepTutorBackup` is not inside
  `D:\DeepTutor`. Never touch other processes.
- Patches are idempotent text replacements registered in `atril.patches.PATCHES`. Only two states
  are clean: original once and patched absent (pending), or the reverse (applied); anything else
  means DeepTutor changed and is an error, never forced.
- Tests never wait for real time or call real services: fake `time.sleep`/`time.monotonic`,
  `ollama.get_status`, `DeepTutor` methods and `install.run_command`/`install.capture`.
- `deeptutor doctor` does not accept `--home`; pass it explicitly only to `init`, `config`,
  `start` and `stop`, and rely on `DEEPTUTOR_HOME` (from `DeepTutor.env()`) for the rest.
- DeepTutor settings come from `atril.toml` (no `setup.json`): `config apply` for LLM, embedding,
  search and ports; `install._SETTINGS_SCRIPT`, run with `app/`'s Python, for parser, chunks and
  embedding pace (`batch_size`/`batch_delay` of the active embedding profile, which `config apply`
  rewrites); `kb indexar` reapplies it before indexing.
- `app/` is a shallow clone: update with `fetch --depth 1` + `reset --hard FETCH_HEAD`, only on a
  clean tree, after reverting patches and after checking that `origin` and the current branch match
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
  re-add, then `POST /reindex` with the active `embedding_model`. Success of an add is a **new**
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

## Project rules (load-bearing)

- **One `uv.lock` and one venv** at the project root.
- **Use `uv sync`**: resolves the current project and its `dev` group.
- **Run tools from the root** so they cover all code.
- Package dependencies go in its `pyproject.toml` (`dependencies` and `dependency-groups.dev`).
- To add dependencies: `uv add <pkg>` (runtime) or `uv add --dev <pkg>` (dev).

## Tools and canonical commands

Do not use `pip install` directly.

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

### Optional poe tasks

`[tool.poe]` in `pyproject.toml` defines shortcuts for developers who have Poe the Poet
installed globally (`uv tool install poethepoet`). `poethepoet` is **not** a project
dependency, and nothing (CI, hooks, docs) may require it: every task must also be runnable
with plain `uv run`.

- `executor.type = "uv"` makes poe run each task through `uv run`, so tasks use the
  project's venv.
- `poe check`: `ruff format --check`, `ruff check`, `ty check`, `pytest` (same as CI).
- `poe fix`: `ruff format` and `ruff check --fix`.
- Keep tasks thin wrappers over existing commands. Do not add logic that only exists in poe.

## Agent workflow

1. Before changing, read `README.md`, `pyproject.toml`, `CLAUDE.md`, `docs/decisiones.md`,
   and related tests.
2. Make the smallest necessary change. Do not refactor unrelated code.
3. If you need a new dependency, justify it. If stdlib solves it, do not add it.
4. Do not modify CI, global config, or structure unless the task requires it.
5. Before finishing, run quality commands from the root and fix until they pass.
6. If something fails and you cannot resolve it, show the exact error and propose the minimal fix.
7. Do not leave secrets, temporary files, or TODOs without context.

## Code rules

- Follow PEP 8 and Pythonic style with strict type annotations.
- Use module `acodo` as the utility library.
- Google-style docstrings for public identifiers: complete, with examples when they add value.
- For private identifiers, use brief docstrings.
- Do not repeat obvious things in docstrings or add unnecessary examples.
- Avoid overengineering. Prefer simple and explicit solutions.
- Keep functions and classes small, with clear English names.

Example of a public docstring:

```python
def sum_numbers(a: int, b: int) -> int:
    """Suma dos números enteros.

    Args:
        a: Primer número.
        b: Segundo número.

    Returns:
        La suma de ``a`` y ``b``.

    Examples:
        >>> sum_numbers(2, 3)
        5
    """
    return a + b
```

## Tests

- Use `pytest`.
- Cover relevant logic and fixed bugs.
- Do not chase 100% coverage. Prioritize useful and readable tests.
- Tests must pass on Linux and Windows.
- Test files live in `tests/`. Run `uv run pytest` from the root.

## CI

- GitHub Actions on `ubuntu-latest` and `windows-latest`.
- Minimum steps from the root:
  - `uv sync --locked`
  - `uv run ruff format --check .`
  - `uv run ruff check .`
  - `uv run ty check`
  - `uv run pytest`
- Python versions come from the CI matrix and `requires-python` in `pyproject.toml`.
- Use `astral-sh/setup-uv` to install `uv`.

## Commits

- Never commit automatically; report success and wait for confirmation.
- Use Conventional Commits in Spanish.
- Examples:
  - `feat: añade cálculo de totales`
  - `fix: corrige validación de entrada`
  - `docs: actualiza CHANGELOG para 0.1.1`
  - `test: cubre casos límite`
  - `chore: bump versión a 0.2.0`
- Atomic commit explaining the _why_, not just the _what_.
- Do not mix unrelated changes.

## Definition of done

A task is done when:

- `uv run ruff format --check .` passes without errors.
- `uv run ruff check .` passes without errors.
- `uv run ty check` passes without errors.
- `uv run pytest` passes without errors.
- Documentation and README updated if API or usage changes.
- Project version bumped in `pyproject.toml` and `CHANGELOG.md` updated (required before push).

## Publishing

`publish.yml` publishes to PyPI (trusted publishing, no token) on every push to `main` that
touches `src/`, `pyproject.toml`, `README.md` or `LICENSE`, unless the tag `vX.Y.Z` of the
current version already exists; it then creates that tag and a GitHub release. So a push that
changes the package **must** bump the version, or nothing is published. `README.md` is the PyPI
page: use absolute GitHub URLs for links.

## Versioning and changelog (pre-push)

Before any `git push` with code changes:

1. **Bump version** in `pyproject.toml` following SemVer:
   - **MAJOR**: breaking changes to public API.
   - **MINOR**: new backward-compatible functionality.
   - **PATCH**: bug fixes, internal refactors, docs affecting published package.
2. **Update `CHANGELOG.md`** (Keep a Changelog):
   - Entries under `## [Unreleased]` while working, or promote to `## [X.Y.Z] - YYYY-MM-DD` on
     bump.
   - Group under `### Added`, `### Changed`, `### Fixed`, `### Removed`, `### Deprecated`,
     `### Security`.
   - Write in Spanish, imperative or past tense, explaining the _why_.
3. **Lockfile consistency**: if bump changes dep constraints, update `pyproject.toml`, run
   `uv sync`, commit updated `uv.lock`.
4. **Atomic release commit** before push:
   - `chore: bump versión a X.Y.Z`
   - `docs: actualiza CHANGELOG para X.Y.Z`
     Or a single combined commit if change and release are inseparable.

If unsure whether a change is breaking, ask the user before choosing MAJOR. When in doubt between
PATCH and MINOR, prefer MINOR.

## Limits

- Do not modify `CLAUDE.md` without justified reason.
- Do not use `pip install` directly.
- Do not use `uv sync --all-packages` (for workspaces, not standalone projects).
- Do not add unnecessary dependencies.
- Do not change CI, Ruff, ty or pytest without justification.
- Do not format files unrelated to the change.
- Do not rewrite code unnecessarily.
- If you cannot ask, choose the minimal change and document the assumption in the commit or PR.
