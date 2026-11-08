"""Apartado Biblioteca: todas las fuentes de todos los temarios, con búsqueda."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from atril.checks import Finding, Level, ok
from atril.config import Syllabus, load_syllabus
from atril.gui import style
from atril.gui.desktop import open_path
from atril.gui.dialogs import ask_choice, ask_text
from atril.gui.model import SourceRow, SyllabusData, filter_rows, load_all, source_rows
from atril.ops import Reporter
from atril.ops import sources as source_ops
from atril.ops import syllabus as syllabus_ops
from atril.sources import Outcome, Result

if TYPE_CHECKING:
    from atril.gui.app import App

ALL = "Todos los temarios"
"""Opción del filtro sin temario."""

OUTCOME_LEVELS = {
    Outcome.DOWNLOADED: Level.OK,
    Outcome.UPDATED: Level.WARNING,
    Outcome.UNCHANGED: Level.OK,
    Outcome.PRESENT: Level.INFO,
    Outcome.REMOTE: Level.INFO,
    Outcome.MANUAL: Level.WARNING,
    Outcome.MISSING: Level.WARNING,
    Outcome.FAILED: Level.ERROR,
}
"""Nivel de cada resultado de descarga o comprobación."""


class LibraryView(tk.Frame):
    """Buscador de fuentes, tabla con su estado y acciones para añadir y descargar."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la barra de búsqueda, la tabla y las acciones."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._data: list[SyllabusData] = []
        self._rows: list[SourceRow] = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        card = style.card(self, "Biblioteca")
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)

        search = tk.Frame(card, background=style.CARD)
        search.grid(row=1, column=0, sticky="ew")
        search.columnconfigure(0, weight=1)
        self._query = tk.StringVar(self)
        self._query.trace_add("write", lambda *_: self._show_rows())
        entry = ttk.Entry(search, textvariable=self._query)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._syllabus = tk.StringVar(self, ALL)
        self._filter = ttk.Combobox(
            search, textvariable=self._syllabus, state="readonly", width=28
        )
        self._filter.grid(row=0, column=1)
        self._filter.bind("<<ComboboxSelected>>", lambda _: self._show_rows())

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="w", pady=12)
        actions = (
            ("Añadir PDF…", self.add_files, True),
            ("Añadir URL…", self.add_url, False),
            ("Descargar lo que falta", self.download, False),
            ("Buscar versiones nuevas", self.check, False),
        )
        for column, (text, command, accent) in enumerate(actions):
            app.action(
                ttk.Button(
                    tools,
                    text=text,
                    command=command,
                    style="Accent.TButton" if accent else "TButton",
                )
            ).grid(row=0, column=column, padx=(0, 8))
        app.cancel_button(ttk.Button(tools, text="Cancelar", command=app.cancel)).grid(
            row=0, column=len(actions), padx=(0, 8)
        )
        ttk.Button(tools, text="Abrir carpeta", command=self.open_folder).grid(
            row=0, column=len(actions) + 1
        )

        table = tk.Frame(card, background=style.CARD)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("titulo", "temario", "kb", "estado")
        self._table = ttk.Treeview(table, columns=columns, show="headings")
        for column, (title, width) in zip(
            columns,
            (("Fuente", 320), ("Temario", 180), ("Base", 150), ("Estado", 160)),
            strict=True,
        ):
            self._table.heading(column, text=title, anchor="w")
            self._table.column(
                column,
                width=round(width * style.scale(self)),
                anchor="w",
                stretch=column == "titulo",
            )
        style.tag_levels(self._table)
        self._table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, command=self._table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._table.configure(yscrollcommand=scroll.set)
        self._count = style.label(card, "", color=style.MUTED, font=style.SMALL)
        self._count.grid(row=4, column=0, sticky="w", pady=(8, 0))

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> None:
        """Lee todas las fuentes y su estado en segundo plano."""
        station = self.app.station
        self.app.run(
            "Leyendo la biblioteca...",
            lambda reporter: load_all(station),
            self._show,
            quiet=True,
        )

    def filter_syllabus(self, syllabus_id: str) -> None:
        """Muestra solo las fuentes de un temario."""
        for item in self._data:
            if item.syllabus.id == syllabus_id:
                self._syllabus.set(item.syllabus.name)
        self._pending_filter = syllabus_id
        self._show_rows()

    def _show(self, data: list[SyllabusData]) -> None:
        """Guarda los datos y pinta la tabla con el filtro actual."""
        self._data = data
        self._rows = source_rows(data)
        self._filter.configure(values=[ALL, *(d.syllabus.name for d in data)])
        wanted = getattr(self, "_pending_filter", None)
        if wanted:
            self.filter_syllabus(wanted)
            self._pending_filter = None
        self._show_rows()

    def _show_rows(self) -> None:
        """Pinta las fuentes que cumplen la búsqueda y el filtro."""
        self._table.delete(*self._table.get_children())
        syllabus = self._current_syllabus()
        rows = filter_rows(
            self._rows, self._query.get(), syllabus.id if syllabus else None
        )
        for row in rows:
            self._table.insert(
                "",
                "end",
                values=(row.title, row.syllabus_name, row.kb_id, row.state),
                tags=(row.level.value,),
            )
        self._count.configure(text=f"{len(rows)} de {len(self._rows)} fuentes")

    def _current_syllabus(self) -> Syllabus | None:
        """Temario del filtro (``None`` = todos)."""
        name = self._syllabus.get()
        return next((d.syllabus for d in self._data if d.syllabus.name == name), None)

    def _target(self) -> Syllabus | None:
        """Temario donde añadir: el del filtro o el que elija el usuario."""
        current = self._current_syllabus()
        if current is not None:
            return current
        if not self._data:
            messagebox.showinfo(
                "Atril", "Crea antes un temario (apartado Temarios).", parent=self
            )
            return None
        if len(self._data) == 1:
            return self._data[0].syllabus
        chosen = ask_choice(
            self,
            "Temario",
            "¿A qué temario va?",
            [(d.syllabus.id, d.syllabus.name) for d in self._data],
        )
        return next((d.syllabus for d in self._data if d.syllabus.id == chosen), None)

    def _ask_kb(self, syllabus: Syllabus) -> str | None:
        """KB de destino: la única o la que elija el usuario."""
        ids = [kb.id for kb in syllabus.knowledge_bases]
        if len(ids) == 1:
            return ids[0]
        return ask_choice(
            self,
            "Base de conocimiento",
            "¿En qué base de conocimiento va?",
            [(kb.id, kb.description or kb.id) for kb in syllabus.knowledge_bases],
        )

    # --- acciones ---------------------------------------------------------------

    def add_files(self) -> None:
        """Copia uno o varios PDF a un temario."""
        syllabus = self._target()
        if syllabus is None:
            return
        paths = filedialog.askopenfilenames(
            title="PDF para la biblioteca",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            parent=self,
        )
        kb_id = self._ask_kb(syllabus) if paths else None
        if not paths or kb_id is None:
            return

        def add(reporter: Reporter) -> None:
            for path in paths:
                source = syllabus_ops.add_source(syllabus, path, kb_id=kb_id)
                reporter.show([ok(f"Añadida {source.id}.")])
            reporter.show([ok(f"{len(paths)} PDF añadidos; indexa el temario.")])

        self.app.run(
            "Añadiendo PDF...", add, lambda _: self.refresh(), title="Añadir PDF"
        )

    def add_url(self) -> None:
        """Declara una fuente PDF por su URL y la descarga."""
        syllabus = self._target()
        if syllabus is None:
            return
        url = ask_text(self, "Añadir URL", "Dirección (http/https) del PDF:")
        if not url:
            return
        title = ask_text(self, "Añadir URL", "Título (opcional):") or None
        kb_id = self._ask_kb(syllabus)
        if kb_id is None:
            return
        cancel = self.app.worker.cancel

        def add(reporter: Reporter) -> None:
            source = syllabus_ops.add_source(syllabus, url, title=title, kb_id=kb_id)
            fresh = load_syllabus(syllabus.root)
            results = source_ops.download(fresh, reporter, [source.id], cancel)
            _report(reporter, results)

        self.app.run(
            "Añadiendo la URL...", add, lambda _: self.refresh(), title="Añadir URL"
        )

    def download(self) -> None:
        """Descarga las fuentes que faltan (del temario filtrado o de todos)."""
        targets = self._targets()
        cancel = self.app.worker.cancel

        def fetch(reporter: Reporter) -> None:
            results: list[Result] = []
            for syllabus in targets:
                results += source_ops.download(syllabus, reporter, cancel=cancel)
            _report(reporter, results)

        self.app.run(
            "Descargando fuentes...",
            fetch,
            lambda _: self.refresh(),
            title="Descargar fuentes",
        )

    def check(self) -> None:
        """Busca versiones nuevas de las fuentes con URL."""
        targets = self._targets()
        cancel = self.app.worker.cancel

        def look(reporter: Reporter) -> None:
            results: list[Result] = []
            for syllabus in targets:
                found, _ = source_ops.check(
                    syllabus, reporter, check_all=True, cancel=cancel
                )
                results += found
            _report(reporter, results)

        self.app.run(
            "Buscando versiones nuevas...",
            look,
            lambda _: self.refresh(),
            title="Buscar versiones nuevas",
        )

    def open_folder(self) -> None:
        """Abre la carpeta de fuentes del temario filtrado (o la de temarios)."""
        syllabus = self._current_syllabus()
        folder = syllabus.sources_dir if syllabus else self.app.station.syllabi_dir
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def _targets(self) -> list[Syllabus]:
        """Temario filtrado o todos."""
        current = self._current_syllabus()
        return [current] if current else [d.syllabus for d in self._data]


def _report(reporter: Reporter, results: list[Result]) -> None:
    """Resultado de cada fuente y un resumen final."""
    reporter.show(
        [
            Finding(
                OUTCOME_LEVELS[r.outcome],
                f"{r.source.id}: {r.outcome.value}"
                + (f" ({r.detail})" if r.detail else ""),
            )
            for r in results
        ]
    )
    failed = sum(r.outcome is Outcome.FAILED for r in results)
    new = sum(r.outcome in {Outcome.DOWNLOADED, Outcome.UPDATED} for r in results)
    if failed:
        reporter.show(
            [Finding(Level.ERROR, f"{failed} fuentes no se han podido descargar.")]
        )
    else:
        reporter.show([ok(f"{new} fuentes nuevas o actualizadas.")])
