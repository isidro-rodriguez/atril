"""Apartado Biblioteca: las fuentes del temario elegido, con búsqueda y descargas."""

import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from atril.checks import Finding, Level, ok
from atril.config import Syllabus, load_syllabus
from atril.gui import style
from atril.gui.desktop import open_path
from atril.gui.dialogs import ask_choice, ask_text
from atril.gui.model import SourceRow, SyllabusData, filter_rows, load_all, source_rows
from atril.gui.syllabi import SyllabusPicker
from atril.ops import Reporter
from atril.ops import sources as source_ops
from atril.ops import syllabus as syllabus_ops
from atril.sources import Outcome, Result

if TYPE_CHECKING:
    from atril.gui.app import App

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
    """Fuentes del temario elegido, búsqueda y acciones para añadir y descargar."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la cabecera, la tabla y las acciones."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._data: dict[str, SyllabusData] = {}
        self._rows: list[SourceRow] = []
        self._shown: str | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        card = style.card(self, "Biblioteca")
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)

        head = tk.Frame(card, background=style.CARD)
        head.grid(row=1, column=0, sticky="ew")
        head.columnconfigure(2, weight=1)
        self._picker = SyllabusPicker(head, app, self._show_rows)
        self._picker.grid(row=0, column=0, sticky="w", padx=(0, 16))
        self._query = tk.StringVar(self)
        self._query.trace_add("write", lambda *_: self._paint())
        style.label(head, "Buscar", font=style.STRONG).grid(
            row=0, column=1, padx=(0, 10)
        )
        self._search = ttk.Entry(head, textvariable=self._query)
        self._search.grid(row=0, column=2, sticky="ew")

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="w", pady=12)
        self._buttons: list[ttk.Button] = []
        for column, (text, command, accent) in enumerate(
            (
                ("Añadir PDF…", self.add_files, True),
                ("Añadir URL…", self.add_url, False),
                ("Descargar", self.download, False),
                ("Actualizar", self.check, False),
            )
        ):
            button = app.action(
                ttk.Button(
                    tools,
                    text=text,
                    command=command,
                    style="Accent.TButton" if accent else "TButton",
                )
            )
            button.grid(row=0, column=column, padx=(0, 8))
            self._buttons.append(button)
        app.cancel_button(ttk.Button(tools, text="Cancelar", command=app.cancel)).grid(
            row=0, column=4, padx=(0, 8)
        )
        self._open = ttk.Button(tools, text="Abrir carpeta", command=self.open_folder)
        self._open.grid(row=0, column=5)

        table = tk.Frame(card, background=style.CARD)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("titulo", "kb", "estado")
        self._table = ttk.Treeview(table, columns=columns, show="headings")
        for column, (title, width) in zip(
            columns, (("Fuente", 340), ("Base", 180), ("Estado", 160)), strict=True
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
        scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        style.autoscroll(self._table, scroll)
        self._count = style.label(card, "", color=style.MUTED, font=style.SMALL)
        self._count.grid(row=4, column=0, sticky="w", pady=(8, 0))

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Lee los temarios y el estado de sus fuentes en segundo plano."""
        station = self.app.station
        return self.app.run(
            "Leyendo la biblioteca...",
            lambda reporter: load_all(station),
            self._show,
            quiet=True,
        )

    def follow_syllabus(self) -> None:
        """Muestra el temario activo si se eligió en otro apartado."""
        if self._data and self._shown != self.app.syllabus_id:
            self._show(list(self._data.values()))

    def _show(self, data: list[SyllabusData]) -> None:
        """Rellena el desplegable y la tabla del temario activo."""
        self._data = {item.syllabus.id: item for item in data}
        self._picker.fill(data)
        self._show_rows()

    def _show_rows(self) -> None:
        """Filas del temario activo (o la tabla desactivada si no hay ninguno)."""
        self._shown = self.app.syllabus_id
        data = self._data.get(self._shown or "")
        self._rows = source_rows(data) if data else []
        enabled = data is not None
        for widget in (*self._buttons, self._open, self._search, self._table):
            widget.state(["!disabled"] if enabled else ["disabled"])
        self._paint()

    def _paint(self) -> None:
        """Pinta las fuentes que cumplen la búsqueda."""
        self._table.delete(*self._table.get_children())
        if self._current() is None:
            self._count.configure(text="Crea un temario en Temarios para empezar.")
            return
        rows = filter_rows(self._rows, self._query.get())
        for row in rows:
            self._table.insert(
                "",
                "end",
                values=style.cells(row.title, row.kb_id, row.state),
                tags=(row.level.value,),
            )
        self._count.configure(text=f"{len(rows)} de {len(self._rows)} fuentes")

    def _current(self) -> Syllabus | None:
        """Temario activo."""
        data = self._data.get(self.app.syllabus_id or "")
        return data.syllabus if data else None

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
        """Copia uno o varios PDF al temario activo."""
        syllabus = self._current()
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
            reporter.show([ok(f"{len(paths)} PDF añadidos. Indexa el temario.")])

        self.app.run(
            "Añadiendo PDF...", add, lambda _: self.refresh(), title="Añadir PDF"
        )

    def add_url(self) -> None:
        """Declara una fuente PDF por su URL y la descarga."""
        syllabus = self._current()
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
        """Descarga las fuentes que faltan del temario activo."""
        syllabus = self._current()
        if syllabus is None:
            return
        cancel = self.app.worker.cancel

        def fetch(reporter: Reporter) -> None:
            _report(reporter, source_ops.download(syllabus, reporter, cancel=cancel))

        self.app.run(
            "Descargando fuentes...",
            fetch,
            lambda _: self.refresh(),
            title="Descargar fuentes",
        )

    def check(self) -> None:
        """Busca y descarga versiones nuevas de las fuentes con URL."""
        syllabus = self._current()
        if syllabus is None:
            return
        cancel = self.app.worker.cancel

        def look(reporter: Reporter) -> None:
            found, _ = source_ops.check(
                syllabus, reporter, check_all=True, cancel=cancel
            )
            _report(reporter, found)

        self.app.run(
            "Buscando versiones nuevas...",
            look,
            lambda _: self.refresh(),
            title="Actualizar fuentes",
        )

    def open_folder(self) -> None:
        """Abre la carpeta de fuentes del temario activo."""
        syllabus = self._current()
        if syllabus is None:
            return
        syllabus.sources_dir.mkdir(parents=True, exist_ok=True)
        open_path(syllabus.sources_dir)


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
