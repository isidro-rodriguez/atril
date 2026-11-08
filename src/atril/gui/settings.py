"""Apartado Ajustes: todo ``atril.toml`` en pestañas y las herramientas de DeepTutor.

Pestañas: DeepTutor (asistente y búsqueda), Indexado (Ollama y ritmo), Backups,
Avanzado (lo que obliga a reinstalar o reindexar) y Herramientas (instalar,
actualizar, aplicar, diagnosticar). Guardar valida el fichero entero antes de
escribirlo y después dice qué hace falta para que el cambio surta efecto.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from atril import __version__
from atril.checks import Level, error, ok
from atril.config.station import ARCHIVE_FORMATS, PARSERS, Station
from atril.errors import AtrilError
from atril.gui import style
from atril.gui.desktop import open_path
from atril.gui.dialogs import ask_yes_no, show_message
from atril.install import FULL_SHA
from atril.ollama import DEFAULT_URL
from atril.ops import Reporter, service
from atril.ops import installation as installation_ops
from atril.ops import settings as settings_ops
from atril.ops.settings import Effect, Value
from atril.patches import PATCHES

if TYPE_CHECKING:
    from atril.gui.app import App

OLLAMA_DEFAULTS = {
    "url": DEFAULT_URL,
    "embedding": "qwen3-embedding:8b",
    "dimension": 4096,
    "contexto": 8192,
}
"""Valores con los que se activa Ollama si ``atril.toml`` no lo tenía."""


@dataclass(frozen=True, slots=True)
class Field:
    """Una clave de ``atril.toml`` en el formulario."""

    table: str
    key: str
    label: str
    kind: str
    """``text``, ``int``, ``bool``, ``choice``, ``combo`` (con texto libre),
    ``lines``, ``patches`` o ``folders``."""
    current: Callable[[Station], Value]
    help: str = ""
    choices: tuple[str, ...] = ()


def _llm(station: Station, attribute: str) -> str:
    """Proveedor o modelo del asistente ("" si no hay ``[deeptutor.llm]``)."""
    llm = station.deeptutor.llm
    return getattr(llm, attribute) if llm else ""


def _ollama(station: Station, attribute: str, key: str) -> Value:
    """Valor de ``[ollama]`` o el de :data:`OLLAMA_DEFAULTS` si no está."""
    if station.ollama is None:
        return OLLAMA_DEFAULTS[key]
    return getattr(station.ollama, attribute)


TABS: dict[str, tuple[Field, ...]] = {
    "DeepTutor": (
        Field(
            "deeptutor.llm",
            "proveedor",
            "Asistente",
            "combo",
            lambda s: _llm(s, "provider"),
            "Vacío: se configura dentro de DeepTutor. claude_code usa tu sesión de "
            "Claude Code, sin claves.",
            ("", "claude_code"),
        ),
        Field(
            "deeptutor.llm",
            "modelo",
            "Modelo",
            "text",
            lambda s: _llm(s, "model"),
            "Por ejemplo, claude-code/opus.",
        ),
        Field(
            "deeptutor",
            "busqueda",
            "Búsqueda web",
            "combo",
            lambda s: s.deeptutor.search or "",
            "Proveedor de búsqueda de DeepTutor; vacío para no cambiarlo.",
            ("", "duckduckgo"),
        ),
    ),
    "Indexado": (
        Field(
            "ollama",
            "url",
            "Dirección de Ollama",
            "text",
            lambda s: _ollama(s, "url", "url"),
        ),
        Field(
            "indexado",
            "hilos",
            "Hilos",
            "int",
            lambda s: s.indexing.threads,
            "Hilos de cálculo al indexar (0 = sin límite). Menos hilos dejan el "
            "ordenador más libre.",
        ),
        Field(
            "indexado",
            "lote_embedding",
            "Tamaño de lote",
            "int",
            lambda s: s.indexing.batch_size,
            "Fragmentos que se envían juntos a Ollama. Bájalo si falla por memoria.",
        ),
        Field(
            "indexado",
            "pausa_embedding",
            "Pausa (ms)",
            "int",
            lambda s: s.indexing.pause_ms,
            "Pausa entre lotes. Súbela si el ordenador se calienta al indexar.",
        ),
        Field(
            "indexado",
            "descargar_modelos",
            "Modelos del lector",
            "bool",
            lambda s: s.indexing.download_models,
            "Permite que el lector de PDF descargue sus modelos la primera vez.",
        ),
    ),
    "Backups": (
        Field(
            "backup",
            "destinos",
            "Destinos",
            "folders",
            lambda s: [str(p) for p in s.backup.destinations],
            "Carpetas fuera de la estación, mejor en otro disco o sincronizadas. "
            "Un disco desconectado se salta.",
        ),
        Field(
            "backup",
            "formato",
            "Formato",
            "choice",
            lambda s: s.backup.archive_format,
            "zip es más rápido; tar.xz ocupa menos.",
            ARCHIVE_FORMATS,
        ),
        Field(
            "backup",
            "conservar",
            "Conservar",
            "int",
            lambda s: s.backup.keep,
            "Backups que se guardan en cada destino; los más antiguos se borran.",
        ),
    ),
    "Avanzado": (
        Field("deeptutor", "repo", "Repositorio", "text", lambda s: s.deeptutor.repo),
        Field("deeptutor", "rama", "Rama", "text", lambda s: s.deeptutor.branch),
        Field("deeptutor", "python", "Python", "text", lambda s: s.deeptutor.python),
        Field(
            "deeptutor.puertos",
            "backend",
            "Puerto del backend",
            "int",
            lambda s: s.deeptutor.backend_port,
        ),
        Field(
            "deeptutor.puertos",
            "frontend",
            "Puerto del frontend",
            "int",
            lambda s: s.deeptutor.frontend_port,
        ),
        Field(
            "deeptutor",
            "parches",
            "Parches",
            "patches",
            lambda s: list(s.deeptutor.patches),
        ),
        Field(
            "deeptutor",
            "paquetes",
            "Paquetes extra",
            "lines",
            lambda s: list(s.deeptutor.packages),
            "Uno por línea.",
        ),
        Field(
            "ollama",
            "embedding",
            "Modelo de embedding",
            "text",
            lambda s: _ollama(s, "embedding", "embedding"),
        ),
        Field(
            "ollama",
            "dimension",
            "Dimensión",
            "int",
            lambda s: _ollama(s, "dimension", "dimension"),
        ),
        Field(
            "ollama",
            "contexto",
            "Contexto",
            "int",
            lambda s: _ollama(s, "context", "contexto"),
        ),
        Field(
            "indexado",
            "parser",
            "Lector de PDF",
            "choice",
            lambda s: s.indexing.parser,
            choices=tuple(sorted(PARSERS)),
        ),
        Field("indexado", "chunk", "Fragmento", "int", lambda s: s.indexing.chunk_size),
        Field(
            "indexado", "solape", "Solape", "int", lambda s: s.indexing.chunk_overlap
        ),
    ),
}
"""Pestañas del formulario y sus claves (todas las de ``atril.toml``)."""

ADVANCED_SPLIT = 7
"""En Avanzado, las primeras claves van a la izquierda y el resto a la derecha."""

EFFECT_HINTS = {
    Effect.APPLY: "Aplicar la configuración a DeepTutor (botón «Aplicar ahora»).",
    Effect.PATCHES: "Aplicar los parches (se hace con «Aplicar ahora»).",
    Effect.REINSTALL: "Reinstalar DeepTutor: Herramientas > Instalar o reparar.",
    Effect.REINDEX: "Reindexar los temarios: los vectores actuales ya no sirven.",
}
"""Qué decir al alumno después de guardar, por efecto."""


class SettingsView(tk.Frame):
    """Pestañas de ajustes con Guardar y Descartar, y la de herramientas."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las pestañas y la barra de guardar."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._vars: dict[tuple[str, str], tk.Variable] = {}
        self._texts: dict[tuple[str, str], tk.Text] = {}
        self._patches: dict[str, tk.BooleanVar] = {}
        self._folders: tk.Listbox | None = None
        self._use_ollama = tk.BooleanVar(self)
        self._docling = tk.BooleanVar(self, value=True)
        self._commit = tk.StringVar(self)

        self._tabs = ttk.Notebook(self)
        self._tabs.grid(row=0, column=0, sticky="nsew")
        for name, fields in TABS.items():
            tab = tk.Frame(self._tabs, background=style.CARD, padx=20, pady=16)
            tab.columnconfigure(1, weight=1)
            self._tabs.add(tab, text=name)
            if name == "Avanzado":
                self._build_advanced(tab, fields)
            else:
                self._build_fields(tab, fields, start=1 if name == "Indexado" else 0)
            if name == "Indexado":
                ttk.Checkbutton(
                    tab,
                    text="Usar Ollama para indexar fuentes (sin Ollama, DeepTutor "
                    "funciona pero no se indexa nada)",
                    variable=self._use_ollama,
                ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self._build_tools()

        bar = tk.Frame(self, background=style.PAGE)
        bar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        bar.columnconfigure(2, weight=1)
        app.action(
            ttk.Button(bar, text="Guardar", style="Accent.TButton", command=self.save)
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(bar, text="Descartar cambios", command=self.refresh).grid(
            row=0, column=1
        )
        self._note = style.label(bar, "", background=style.PAGE, color=style.MUTED)
        self._note.grid(row=0, column=2, sticky="w", padx=(16, 0))

    # --- construcción -----------------------------------------------------------

    def _build_fields(
        self, tab: tk.Frame, fields: tuple[Field, ...], start: int
    ) -> None:
        """Una fila por clave: nombre, control y explicación debajo."""
        row = start
        for field in fields:
            style.label(tab, field.label, font=style.STRONG).grid(
                row=row, column=0, sticky="nw", padx=(0, 16), pady=(4, 0)
            )
            self._control(tab, field).grid(row=row, column=1, sticky="w", pady=(2, 0))
            row += 1
            if field.help:
                style.label(
                    tab, field.help, color=style.MUTED, font=style.SMALL, wraplength=520
                ).grid(row=row, column=1, sticky="w", pady=(2, 8))
                row += 1

    def _build_advanced(self, tab: tk.Frame, fields: tuple[Field, ...]) -> None:
        """Dos columnas de claves delicadas, con un aviso arriba."""
        style.label(
            tab,
            "  Cambiar esto obliga a reinstalar DeepTutor o a reindexar los temarios.",
            color=style.LEVEL_COLORS[Level.WARNING],
            image=style.icon(self, style.LEVEL_ICONS[Level.WARNING], 18),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)
        for index, field in enumerate(fields):
            column = 0 if index < ADVANCED_SPLIT else 2
            row = 1 + (index if index < ADVANCED_SPLIT else index - ADVANCED_SPLIT)
            style.label(tab, field.label, font=style.STRONG).grid(
                row=row, column=column, sticky="nw", padx=(0, 12), pady=4
            )
            self._control(tab, field).grid(
                row=row, column=column + 1, sticky="w", pady=4, padx=(0, 20)
            )

    def _control(self, parent: tk.Frame, field: Field) -> tk.Widget:
        """Control de una clave según su tipo."""
        key = (field.table, field.key)
        match field.kind:
            case "int":
                var: tk.Variable = tk.StringVar(self)
                widget: tk.Widget = ttk.Spinbox(
                    parent, from_=0, to=99999, textvariable=var, width=10
                )
            case "bool":
                var = tk.BooleanVar(self)
                widget = ttk.Checkbutton(parent, variable=var)
            case "choice":
                var = tk.StringVar(self)
                widget = ttk.Combobox(
                    parent,
                    textvariable=var,
                    values=field.choices,
                    state="readonly",
                    width=16,
                )
            case "combo":
                var = tk.StringVar(self)
                widget = ttk.Combobox(
                    parent, textvariable=var, values=field.choices, width=30
                )
            case "lines":
                text = tk.Text(
                    parent,
                    height=3,
                    width=34,
                    font=style.SMALL,
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=style.BORDER,
                )
                self._texts[key] = text
                return text
            case "patches":
                frame = tk.Frame(parent, background=style.CARD)
                for row, name in enumerate(sorted(PATCHES)):
                    flag = tk.BooleanVar(self)
                    self._patches[name] = flag
                    ttk.Checkbutton(frame, text=name, variable=flag).grid(
                        row=row, column=0, sticky="w"
                    )
                return frame
            case "folders":
                return self._folder_list(parent)
            case _:
                var = tk.StringVar(self)
                width = 40 if field.table != "deeptutor" else 34
                widget = ttk.Entry(parent, textvariable=var, width=width)
        self._vars[key] = var
        return widget

    def _folder_list(self, parent: tk.Frame) -> tk.Frame:
        """Lista de carpetas con botones para añadir y quitar."""
        frame = tk.Frame(parent, background=style.CARD)
        self._folders = tk.Listbox(
            frame,
            height=3,
            width=46,
            font=style.BODY,
            activestyle="none",
            relief="flat",
            highlightthickness=1,
            highlightbackground=style.BORDER,
            background=style.CARD,
            foreground=style.TEXT,
        )
        self._folders.grid(row=0, column=0, rowspan=2, sticky="w")
        ttk.Button(frame, text="Añadir…", command=self.add_folder).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )
        ttk.Button(frame, text="Quitar", command=self.remove_folder).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0)
        )
        return frame

    def _build_tools(self) -> None:
        """Pestaña Herramientas: mantenimiento de DeepTutor y de la configuración."""
        tab = tk.Frame(self._tabs, background=style.CARD, padx=20, pady=16)
        tab.columnconfigure(1, weight=1)
        self._tabs.add(tab, text="Herramientas")
        rows: tuple[tuple[str, str, Callable[[], None]], ...] = (
            (
                "Instalar o reparar",
                "Instala DeepTutor o completa una instalación a medias.",
                self.install,
            ),
            (
                "Actualizar DeepTutor",
                "Trae la última versión de su rama y lo deja configurado.",
                self.update_deeptutor,
            ),
            (
                "Aplicar ajustes",
                "Lleva estos ajustes y los parches a DeepTutor sin reinstalar.",
                self.apply,
            ),
            (
                "Diagnóstico",
                "Comprueba la instalación de DeepTutor.",
                self.doctor,
            ),
            (
                "Validar configuración",
                "Revisa atril.toml y el temario.toml de cada temario.",
                self.validate,
            ),
            (
                "Copiar informe",
                "Copia un informe técnico para pedir ayuda.",
                self.copy_report,
            ),
        )
        for row, (title, text, command) in enumerate(rows):
            self.app.action(ttk.Button(tab, text=title, command=command)).grid(
                row=row, column=0, sticky="ew", pady=3, padx=(0, 14)
            )
            style.label(tab, text, color=style.MUTED).grid(
                row=row, column=1, sticky="w"
            )
        start = len(rows)
        ttk.Checkbutton(
            tab,
            text="Instalar Docling (lee mejor los PDF; descarga grande)",
            variable=self._docling,
        ).grid(row=start, column=0, columnspan=2, sticky="w", pady=(8, 0))
        commit = tk.Frame(tab, background=style.CARD)
        commit.grid(row=start + 1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        style.label(commit, "Volver al commit", font=style.STRONG).grid(
            row=0, column=0, padx=(0, 10)
        )
        ttk.Entry(commit, textvariable=self._commit, width=44).grid(
            row=0, column=1, padx=(0, 8)
        )
        self.app.action(ttk.Button(commit, text="Volver", command=self.rollback)).grid(
            row=0, column=2
        )
        files = tk.Frame(tab, background=style.CARD)
        files.grid(row=start + 2, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Button(files, text="Abrir registros", command=self.open_logs).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(files, text="Abrir atril.toml", command=self.open_config).grid(
            row=0, column=1
        )

    # --- valores ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Carga los valores actuales de la estación (descarta lo no guardado)."""
        station = self.app.station
        self._use_ollama.set(station.ollama is not None)
        for fields in TABS.values():
            for field in fields:
                value = field.current(station)
                key = (field.table, field.key)
                if field.kind == "lines":
                    text = self._texts[key]
                    text.delete("1.0", "end")
                    text.insert("1.0", "\n".join(_strings(value)))
                elif field.kind == "patches":
                    for name, flag in self._patches.items():
                        flag.set(name in _strings(value))
                elif field.kind == "folders" and self._folders is not None:
                    self._folders.delete(0, "end")
                    for folder in _strings(value):
                        self._folders.insert("end", folder)
                else:
                    self._vars[key].set(value)
        self._note.configure(text="")
        return True

    def _value(self, field: Field) -> Value:
        """Valor del formulario para ``field``.

        Raises:
            ValueError: Si un número no es válido.
        """
        key = (field.table, field.key)
        match field.kind:
            case "lines":
                text = self._texts[key].get("1.0", "end")
                return [line.strip() for line in text.splitlines() if line.strip()]
            case "patches":
                return [name for name, flag in self._patches.items() if flag.get()]
            case "folders":
                folders = self._folders.get(0, "end") if self._folders else ()
                return [str(folder) for folder in folders]
            case "int":
                raw = str(self._vars[key].get()).strip()
                if not raw.isdigit():
                    raise ValueError(f"«{field.label}» debe ser un número entero.")
                return int(raw)
            case "bool":
                return bool(self._vars[key].get())
            case _:
                return str(self._vars[key].get()).strip()

    def changes(self) -> settings_ops.Changes:
        """Cambios del formulario respecto a la estación actual.

        Raises:
            ValueError: Si un número no es válido.
        """
        station = self.app.station
        found: dict[str, dict[str, Value | None] | None] = {}
        use_ollama = self._use_ollama.get()
        for fields in TABS.values():
            for field in fields:
                if field.table == "ollama" and not use_ollama:
                    continue
                value = self._value(field)
                adding_ollama = field.table == "ollama" and station.ollama is None
                if value == field.current(station) and not adding_ollama:
                    continue
                table = found.setdefault(field.table, {})
                assert table is not None
                table[field.key] = None if value == "" else value
        if not use_ollama and station.ollama is not None:
            found["ollama"] = None
        llm = found.get("deeptutor.llm")
        if llm is not None:
            provider = llm.get("proveedor", _llm(station, "provider")) or ""
            model = llm.get("modelo", _llm(station, "model")) or ""
            if not provider and not model:
                found["deeptutor.llm"] = None
        return found

    # --- acciones -----------------------------------------------------------------

    def save(self) -> None:
        """Valida y guarda; después dice qué falta para que surta efecto."""
        try:
            changes = self.changes()
        except ValueError as exc:
            show_message(self, "Ajustes", str(exc), Level.WARNING)
            return
        if not changes:
            self._note.configure(text="No hay cambios.")
            return
        before = self.app.station
        try:
            after = settings_ops.update(before, changes)
        except AtrilError as exc:
            show_message(self, "No se ha guardado", _sentence(str(exc)), Level.ERROR)
            return
        self.app.station = after
        self.refresh()
        self._note.configure(text="Guardado.")
        self.app.log(Level.OK, "Ajustes guardados")
        effects = settings_ops.effects(before, after)
        if not effects:
            return
        lines = "\n".join(f"• {EFFECT_HINTS[effect]}" for effect in effects)
        applicable = {Effect.APPLY, Effect.PATCHES} & set(effects)
        if applicable and ask_yes_no(
            self,
            "Para que surta efecto",
            f"Hace falta:\n{lines}",
            "Aplicar ahora",
            level=Level.INFO,
        ):
            self.apply()
        elif not applicable:
            show_message(self, "Para que surta efecto", f"Hace falta:\n{lines}")

    def add_folder(self) -> None:
        """Añade un destino de backups elegido con el explorador."""
        if self._folders is None:
            return
        folder = filedialog.askdirectory(parent=self, title="Carpeta para los backups")
        if folder and str(Path(folder)) not in self._folders.get(0, "end"):
            self._folders.insert("end", str(Path(folder)))

    def remove_folder(self) -> None:
        """Quita el destino seleccionado."""
        if self._folders is None:
            return
        for index in reversed(self._folders.curselection()):
            self._folders.delete(index)

    def install(self) -> None:
        """Instala DeepTutor o completa la instalación."""
        if not ask_yes_no(
            self,
            "Instalar o reparar DeepTutor",
            "Se descargará lo que falte (varios GB con Docling). Puede tardar "
            "bastante. DeepTutor debe estar parado.",
            "Instalar",
        ):
            return
        station, docling = self.app.station, self._docling.get()

        def run(reporter: Reporter) -> None:
            installation_ops.install_deeptutor(station, reporter, docling=docling)
            reporter.show([ok("DeepTutor instalado.")])

        self.app.run(
            "Instalando DeepTutor...", run, _nothing, title="Instalar DeepTutor"
        )

    def update_deeptutor(self, commit: str | None = None) -> None:
        """Actualiza DeepTutor (o lo lleva a ``commit``)."""
        station, docling = self.app.station, self._docling.get()

        def run(reporter: Reporter) -> str | None:
            result = installation_ops.update_deeptutor(
                station, reporter, docling=docling, commit=commit
            )
            if not result.changed:
                reporter.show([ok("Ya está en la última versión.")])
                return None
            reporter.show(
                [
                    ok(
                        "DeepTutor actualizado. Si da problemas, «Volver» lleva a la "
                        "versión anterior."
                    )
                ]
            )
            return result.previous

        def done(previous: str | None) -> None:
            if previous:
                self._commit.set(previous)

        self.app.run(
            "Actualizando DeepTutor...", run, done, title="Actualizar DeepTutor"
        )

    def rollback(self) -> None:
        """Lleva DeepTutor al commit indicado, tras confirmarlo."""
        commit = self._commit.get().strip().lower()
        if not FULL_SHA.fullmatch(commit):
            show_message(
                self,
                "Volver a una versión",
                "Escribe el commit completo: 40 caracteres 0-9 a-f.",
                Level.WARNING,
            )
            return
        if ask_yes_no(
            self,
            "Volver a una versión",
            f"DeepTutor se parará y pasará al commit {commit[:12]}.",
            "Volver",
            level=Level.WARNING,
        ):
            self.update_deeptutor(commit)

    def apply(self) -> None:
        """Aplica ``atril.toml`` y los parches a DeepTutor."""
        station = self.app.station

        def run(reporter: Reporter) -> None:
            installation_ops.apply_settings(station, reporter)
            reporter.show([ok("Ajustes aplicados a DeepTutor.")])

        self.app.run("Aplicando ajustes...", run, _nothing, title="Aplicar ajustes")

    def doctor(self) -> None:
        """Pasa el diagnóstico de DeepTutor."""
        station = self.app.station
        self.app.run(
            "Diagnosticando DeepTutor...",
            lambda reporter: reporter.show(installation_ops.doctor(station, reporter)),
            _nothing,
            title="Diagnóstico de DeepTutor",
        )

    def validate(self) -> None:
        """Valida la configuración de la estación y de los temarios."""
        station = self.app.station

        def run(reporter: Reporter) -> None:
            syllabi, errors = installation_ops.validate(station)
            reporter.show(
                [
                    ok("atril.toml correcto."),
                    *(ok(f"Temario «{s.name}» correcto.") for s in syllabi),
                    *(error(message) for message in errors),
                ]
            )

        self.app.run("Validando...", run, _nothing, title="Validar configuración")

    def copy_report(self) -> None:
        """Copia al portapapeles un informe técnico (rutas, versiones, estado)."""
        station = self.app.station

        def run(reporter: Reporter) -> str:
            lines = [f"atril {__version__}", f"Estación: {station.root}"]
            for title, findings in service.status(station, reporter):
                lines.append(f"— {title}")
                lines += [f"{f.level.value}: {f.message}" for f in findings]
            lines.append("— Herramientas")
            lines += [
                f"{t.name}: {t.path or 'no encontrado'}"
                for t in installation_ops.tools()
            ]
            return "\n".join(lines)

        def copied(report: str) -> None:
            self.clipboard_clear()
            self.clipboard_append(report)
            show_message(self, "Copiar informe", "Informe copiado al portapapeles.")

        self.app.run("Preparando el informe...", run, copied, quiet=True)

    def open_logs(self) -> None:
        """Abre la carpeta de registros de atril."""
        logs = self.app.station.logs_dir
        open_path(logs if logs.is_dir() else self.app.station.data_dir)

    def open_config(self) -> None:
        """Abre ``atril.toml`` con el editor del sistema."""
        open_path(self.app.station.config_file)


def _strings(value: Value) -> list[str]:
    """Lista de textos de un valor (vacía si no es una lista)."""
    return [str(item) for item in value] if isinstance(value, list) else []


def _sentence(text: str) -> str:
    """Primera letra en mayúscula."""
    return text[:1].upper() + text[1:]


def _nothing(_: object) -> None:
    """Sin nada que hacer al terminar."""
