"""Apartado Diagnóstico: estado detallado, herramientas de DeepTutor e historial.

Aquí sí hay rutas y detalles técnicos: es lo que se copia al pedir ayuda.
"""

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from atril import __version__
from atril.checks import Finding, Level, error, ok
from atril.gui import style
from atril.gui.activity import Event, when_label
from atril.gui.desktop import open_path
from atril.gui.services import ServicesView
from atril.install import FULL_SHA
from atril.ops import Reporter, service
from atril.ops import installation as installation_ops
from atril.ops.service import Section

if TYPE_CHECKING:
    from atril.gui.app import App


def detail_lines(sections: list[Section], station_root: str) -> list[tuple[Level, str]]:
    """Informe técnico completo: versión, estación y cada comprobación."""
    lines = [
        (Level.INFO, f"atril {__version__}"),
        (Level.INFO, f"Estación: {station_root}"),
    ]
    for title, findings in sections:
        lines.append((Level.INFO, f"— {title}"))
        lines.extend((finding.level, finding.message) for finding in findings)
    return lines


class DiagnosticsView(tk.Frame):
    """Pestañas Estado, Herramientas e Historial."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las tres pestañas."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._tabs = ttk.Notebook(self)
        self._tabs.grid(row=0, column=0, sticky="nsew")
        self._status = self._text_tab("Estado")
        self._build_tools()
        self._build_history()

    # --- Estado -------------------------------------------------------------

    def _text_tab(self, title: str) -> tk.Text:
        """Pestaña con un texto de solo lectura y un botón de copiar."""
        tab = tk.Frame(self._tabs, background=style.CARD, padx=16, pady=12)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self._tabs.add(tab, text=title)
        bar = tk.Frame(tab, background=style.CARD)
        bar.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.app.action(
            ttk.Button(bar, text="Volver a comprobar", command=self.refresh)
        ).grid(row=0, column=0, padx=(0, 8))
        text = _readonly_text(tab)
        ttk.Button(bar, text="Copiar informe", command=lambda: self._copy(text)).grid(
            row=0, column=1
        )
        text.grid(row=1, column=0, sticky="nsew")
        return text

    def refresh(self) -> None:
        """Comprueba todo con detalle (rutas incluidas)."""
        station = self.app.station

        def run(reporter: Reporter) -> list[tuple[Level, str]]:
            lines = detail_lines(service.status(station, reporter), str(station.root))
            lines.append((Level.INFO, "— Herramientas"))
            for tool in installation_ops.tools():
                level = (
                    Level.OK
                    if tool.path
                    else (Level.ERROR if tool.required else Level.WARNING)
                )
                lines.append((level, f"{tool.name}: {tool.path or 'no encontrado'}"))
            return lines

        self.app.run("Comprobando...", run, self._show_status, quiet=True)
        self._fill_history()

    def _show_status(self, lines: list[tuple[Level, str]]) -> None:
        """Pinta el informe técnico."""
        _write(self._status, lines)

    def _copy(self, text: tk.Text) -> None:
        """Copia el contenido al portapapeles (para pedir ayuda)."""
        self.clipboard_clear()
        self.clipboard_append(text.get("1.0", "end").strip())

    # --- Herramientas ---------------------------------------------------------

    def _build_tools(self) -> None:
        """Acciones avanzadas sobre DeepTutor y la configuración."""
        tab = tk.Frame(self._tabs, background=style.CARD, padx=16, pady=12)
        tab.columnconfigure(1, weight=1)
        self._tabs.add(tab, text="Herramientas")
        rows = (
            ("Diagnóstico de DeepTutor", "Ejecuta «deeptutor doctor».", self.doctor),
            (
                "Aplicar parches",
                "Reaplica los parches de atril.toml (DeepTutor parado).",
                self.patches,
            ),
            (
                "Validar configuración",
                "Comprueba atril.toml y el temario.toml de cada temario.",
                self.validate,
            ),
        )
        for row, (title, text, command) in enumerate(rows):
            self.app.action(ttk.Button(tab, text=title, command=command)).grid(
                row=row, column=0, sticky="ew", pady=4, padx=(0, 12)
            )
            style.label(tab, text, color=style.MUTED).grid(
                row=row, column=1, sticky="w"
            )
        start = len(rows)
        style.label(tab, "Volver a una versión de DeepTutor", font=style.STRONG).grid(
            row=start, column=0, columnspan=2, sticky="w", pady=(18, 4)
        )
        commit_row = tk.Frame(tab, background=style.CARD)
        commit_row.grid(row=start + 1, column=0, columnspan=2, sticky="w")
        self._commit = tk.StringVar(master=self)
        ttk.Entry(commit_row, textvariable=self._commit, width=44).grid(
            row=0, column=0, padx=(0, 8)
        )
        self.app.action(
            ttk.Button(commit_row, text="Volver a este commit", command=self.rollback)
        ).grid(row=0, column=1)
        style.label(
            tab,
            "Pega el commit completo (40 caracteres) que indicó la última "
            "actualización.",
            color=style.MUTED,
            font=style.SMALL,
        ).grid(row=start + 2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        files = tk.Frame(tab, background=style.CARD)
        files.grid(row=start + 3, column=0, columnspan=2, sticky="w", pady=(18, 0))
        ttk.Button(files, text="Abrir registros", command=self.open_logs).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(files, text="Abrir atril.toml", command=self.open_config).grid(
            row=0, column=1
        )

    def doctor(self) -> None:
        """Pasa ``deeptutor doctor``."""
        station = self.app.station
        self.app.run(
            "Diagnosticando DeepTutor...",
            lambda reporter: reporter.show(installation_ops.doctor(station, reporter)),
            lambda _: None,
            title="Diagnóstico de DeepTutor",
        )

    def patches(self) -> None:
        """Aplica los parches configurados."""
        station = self.app.station
        self.app.run(
            "Aplicando parches...",
            lambda reporter: reporter.show(installation_ops.apply_patches(station)),
            lambda _: None,
            title="Aplicar parches",
        )

    def validate(self) -> None:
        """Valida la configuración de la estación y de los temarios."""
        station = self.app.station

        def run(reporter: Reporter) -> None:
            syllabi, errors = installation_ops.validate(station)
            findings: list[Finding] = [ok(f"atril.toml correcto: {station.root}.")]
            findings += [ok(f"Temario «{s.name}» correcto.") for s in syllabi]
            findings += [error(message) for message in errors]
            reporter.show(findings)

        self.app.run("Validando...", run, lambda _: None, title="Validar configuración")

    def rollback(self) -> None:
        """Lleva DeepTutor al commit indicado, tras confirmarlo."""
        commit = self._commit.get().strip().lower()
        if not FULL_SHA.fullmatch(commit):
            messagebox.showerror(
                "Atril",
                "Escribe el commit completo: 40 caracteres 0-9 a-f.",
                parent=self,
            )
            return
        if messagebox.askyesno(
            "Volver a una versión",
            f"DeepTutor se parará y pasará al commit {commit[:12]}. ¿Seguir?",
            parent=self,
        ):
            services = self.app.views["Servicios"]
            if isinstance(services, ServicesView):
                services.update_deeptutor(commit)

    def open_logs(self) -> None:
        """Abre la carpeta de registros de atril."""
        logs = self.app.station.logs_dir
        open_path(logs if logs.is_dir() else self.app.station.data_dir)

    def open_config(self) -> None:
        """Abre ``atril.toml`` con el editor del sistema."""
        open_path(self.app.station.config_file)

    # --- Historial ------------------------------------------------------------

    def _build_history(self) -> None:
        """Lista de operaciones y su detalle técnico."""
        tab = tk.Frame(self._tabs, background=style.CARD, padx=16, pady=12)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self._tabs.add(tab, text="Historial")
        self._history_tab = tab
        columns = ("cuando", "operacion", "resultado")
        self._history = ttk.Treeview(tab, columns=columns, show="headings", height=10)
        for column, title, width in zip(
            columns, ("Cuándo", "Operación", "Resultado"), (130, 220, 420), strict=True
        ):
            self._history.heading(column, text=title, anchor="w")
            self._history.column(
                column,
                width=round(width * style.scale(self)),
                stretch=column == "resultado",
            )
        style.tag_levels(self._history)
        self._history.grid(row=0, column=0, sticky="nsew")
        self._history.bind("<<TreeviewSelect>>", self._show_event)
        self._event_text = _readonly_text(tab, height=8)
        self._event_text.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self._events: dict[str, Event] = {}

    def show_history(self) -> None:
        """Abre la pestaña Historial (desde «Ver todo»)."""
        self._fill_history()
        self._tabs.select(self._history_tab)

    def _fill_history(self) -> None:
        """Recarga la lista de operaciones."""
        self._history.delete(*self._history.get_children())
        self._events.clear()
        for event in self.app.activity.events:
            when = "ahora" if event.running else when_label(event.when)
            item = self._history.insert(
                "",
                "end",
                values=(when, event.title, event.summary),
                tags=(event.level.value,),
            )
            self._events[item] = event

    def _show_event(self, _: object = None) -> None:
        """Detalle técnico del evento elegido."""
        selected = self._history.selection()
        if not selected or selected[0] not in self._events:
            return
        event = self._events[selected[0]]
        lines = [(Level(value), message) for value, message in event.detail]
        _write(self._event_text, lines or [(event.level, event.summary)])


def _readonly_text(parent: tk.Misc, height: int = 20) -> tk.Text:
    """Texto de solo lectura con colores por nivel."""
    text = tk.Text(
        parent,
        height=height,
        wrap="word",
        font=style.BODY,
        background=style.PAGE,
        foreground=style.TEXT,
        relief="flat",
        padx=10,
        pady=8,
        state="disabled",
    )
    for level, color in style.LEVEL_COLORS.items():
        text.tag_configure(level.value, foreground=color)
    return text


def _write(text: tk.Text, lines: list[tuple[Level, str]]) -> None:
    """Sustituye el contenido de ``text`` por ``lines`` con su símbolo de nivel."""
    text.configure(state="normal")
    text.delete("1.0", "end")
    for level, message in lines:
        text.insert("end", f"{style.LEVEL_SYMBOLS[level]} {message}\n", level.value)
    text.configure(state="disabled")
