"""Apartado Temarios: crear temarios, añadir PDF y mantener sus fuentes indexadas."""

import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

from atril.checks import Finding, Level, ok
from atril.config import Syllabus, load_syllabi, load_syllabus
from atril.config.station import Station
from atril.gui import style
from atril.gui.model import actions_needed, source_rows
from atril.ops import Reporter
from atril.ops import knowledge as knowledge_ops
from atril.ops import sources as source_ops
from atril.ops import syllabus as syllabus_ops
from atril.ops.knowledge import KbStatus
from atril.sources import Outcome, Result

if TYPE_CHECKING:
    from atril.gui.app import App


@dataclass(frozen=True, slots=True)
class SyllabusData:
    """Un temario con el estado de sus KB y lo que tiene pendiente."""

    syllabus: Syllabus
    statuses: list[KbStatus]
    pending: list[Finding]


def load_all(station: Station) -> list[SyllabusData]:
    """Temarios de la estación con su estado (lee ficheros y calcula hashes)."""
    syllabi, _ = load_syllabi(station.syllabi_dir)
    return [SyllabusData(s, *knowledge_ops.status(station, s)) for s in syllabi]


class SyllabiView(tk.Frame):
    """Lista de temarios y, del elegido, sus fuentes y acciones."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la lista de temarios y el detalle del elegido."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._data: dict[str, SyllabusData] = {}
        self._current: str | None = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_list().grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_detail().grid(row=0, column=1, sticky="nsew")

    # --- construcción ---------------------------------------------------------

    def _build_list(self) -> tk.Frame:
        """Tarjeta con los temarios y el botón para crear uno."""
        card = style.card(self, "Temarios")
        card.rowconfigure(1, weight=1)
        self._list = ttk.Treeview(
            card, columns=("nombre",), show="headings", selectmode="browse", height=8
        )
        self._list.heading("nombre", text="Nombre", anchor="w")
        self._list.column("nombre", width=230, anchor="w")
        self._list.grid(row=1, column=0, sticky="nsew")
        self._list.bind("<<TreeviewSelect>>", self._on_select)
        self.app.action(
            ttk.Button(card, text="Nuevo temario…", command=self.new_syllabus)
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))
        return card

    def _build_detail(self) -> tk.Frame:
        """Tarjeta con las fuentes del temario elegido y sus acciones."""
        card = style.card(self, "Fuentes")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        self._title = style.label(
            card, "Elige o crea un temario", background=style.CARD, font=style.STRONG
        )
        self._title.grid(row=1, column=0, sticky="w")

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="ew", pady=8)
        app = self.app
        buttons = [
            ("Añadir PDF…", self.add_files),
            ("Añadir URL…", self.add_url),
            ("Descargar", self.download),
            ("Buscar versiones", self.check),
            ("Indexar", self.index),
            ("Reindexar", self.reindex),
        ]
        self._buttons: dict[str, ttk.Button] = {}
        for index, (text, command) in enumerate(buttons):
            button = app.action(ttk.Button(tools, text=text, command=command))
            button.grid(
                row=index // 4, column=index % 4, sticky="ew", padx=(0, 6), pady=2
            )
            self._buttons[text] = button
        cancel = app.cancel_button(
            ttk.Button(tools, text="Cancelar", command=app.cancel)
        )
        cancel.grid(row=1, column=2, sticky="ew", padx=(0, 6), pady=2)

        table = tk.Frame(card, background=style.CARD)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("fuente", "kb", "fichero", "estado")
        self._table = ttk.Treeview(table, columns=columns, show="headings", height=8)
        for column, (title, width) in zip(
            columns,
            (("Fuente", 170), ("KB", 130), ("Fichero", 200), ("Estado", 140)),
            strict=True,
        ):
            self._table.heading(column, text=title, anchor="w")
            stretch = column == "fichero"
            self._table.column(
                column, width=width, minwidth=80, anchor="w", stretch=stretch
            )
        for level, color in style.LEVEL_COLORS.items():
            self._table.tag_configure(level.value, foreground=color)
        self._table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, command=self._table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._table.configure(yscrollcommand=scroll.set)

        self._pending = style.label(
            card, background=style.CARD, color=style.MUTED, wraplength=640
        )
        self._pending.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            card, text="Abrir carpeta del temario", command=self.open_folder
        ).grid(row=5, column=0, sticky="w", pady=(8, 0))
        return card

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> None:
        """Vuelve a leer los temarios y su estado en segundo plano."""
        station = self.app.station
        self.app.run(
            "Leyendo temarios...",
            lambda reporter: load_all(station),
            self._show,
            quiet=True,
        )

    def _show(self, data: list[SyllabusData]) -> None:
        """Pinta la lista de temarios y mantiene el elegido."""
        self._data = {item.syllabus.id: item for item in data}
        self._list.delete(*self._list.get_children())
        for item in data:
            self._list.insert(
                "", "end", iid=item.syllabus.id, values=(item.syllabus.name,)
            )
        if self._current not in self._data:
            self._current = data[0].syllabus.id if data else None
        if self._current:
            self._list.selection_set(self._current)
        self._show_detail()

    def _on_select(self, _: object) -> None:
        """Cambia el temario elegido."""
        selected = self._list.selection()
        if selected and selected[0] != self._current:
            self._current = selected[0]
            self._show_detail()

    def _show_detail(self) -> None:
        """Fuentes del temario elegido, con su estado de indexado."""
        self._table.delete(*self._table.get_children())
        data = self._data.get(self._current or "")
        if data is None:
            self._title.configure(text="Elige o crea un temario")
            self._pending.configure(text="")
            return
        syllabus = data.syllabus
        self._title.configure(text=f"{syllabus.name}  ·  {syllabus.id}")
        several = len(syllabus.knowledge_bases) > 1
        columns = ("fuente", "kb", "fichero", "estado")
        self._table.configure(
            displaycolumns=columns if several else ("fuente", "fichero", "estado")
        )
        for row in source_rows(data.statuses):
            self._table.insert(
                "",
                "end",
                values=(row.source_id, row.kb_id, row.file, row.state),
                tags=(row.level.value,),
            )
        new, stale = actions_needed(data.statuses)
        hints = [finding.message for finding in data.pending]
        if not hints:
            hints = ["Todo indexado." if data.statuses else "Sin KB."]
        self._pending.configure(text="\n".join(hints))
        self._buttons["Indexar"].configure(style="Accent.TButton" if new else "TButton")
        self._buttons["Reindexar"].configure(
            style="Accent.TButton" if stale else "TButton"
        )

    def _selected(self) -> Syllabus | None:
        """Temario elegido; si no hay, lo explica."""
        data = self._data.get(self._current or "")
        if data is None:
            messagebox.showinfo("Atril", "Elige antes un temario.", parent=self)
            return None
        return data.syllabus

    # --- acciones ---------------------------------------------------------------

    def new_syllabus(self) -> None:
        """Crea un temario a partir de su nombre."""
        name = simpledialog.askstring(
            "Nuevo temario", "Nombre del temario:", parent=self
        )
        if not name:
            return
        station = self.app.station

        def created(syllabus: Syllabus) -> None:
            self._current = syllabus.id
            self.app.log(Level.OK, f"Temario {syllabus.name} creado ({syllabus.root}).")
            self.refresh()

        self.app.run(
            "Creando el temario...",
            lambda reporter: syllabus_ops.create(station, name),
            created,
        )

    def add_files(self) -> None:
        """Copia uno o varios PDF al temario elegido."""
        syllabus = self._selected()
        if syllabus is None:
            return
        paths = filedialog.askopenfilenames(
            title="PDF para el temario",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            parent=self,
        )
        kb_id = self._ask_kb(syllabus) if paths else None
        if not paths or kb_id is None:
            return

        def add(reporter: Reporter) -> int:
            for path in paths:
                source = syllabus_ops.add_source(syllabus, path, kb_id=kb_id)
                reporter.show([ok(f"Añadida {source.id} a {kb_id}.")])
            return len(paths)

        self._run("Añadiendo PDF...", add, "Indexa el temario para usarlos.")

    def add_url(self) -> None:
        """Declara una fuente PDF por su URL y la descarga."""
        syllabus = self._selected()
        if syllabus is None:
            return
        url = simpledialog.askstring(
            "Añadir URL", "Dirección (http/https) del PDF:", parent=self
        )
        if not url:
            return
        title = simpledialog.askstring("Añadir URL", "Título (opcional):", parent=self)
        kb_id = self._ask_kb(syllabus)
        if kb_id is None:
            return
        cancel = self.app.worker.cancel

        def add(reporter: Reporter) -> int:
            source = syllabus_ops.add_source(
                syllabus, url.strip(), title=title or None, kb_id=kb_id
            )
            reporter.show([ok(f"Añadida {source.id} a {kb_id}.")])
            fresh = load_syllabus(syllabus.root)
            results = source_ops.download(fresh, reporter, [source.id], cancel)
            _show_results(reporter, results)
            return 1

        self._run("Añadiendo la URL...", add, "Indexa el temario para usarla.")

    def download(self) -> None:
        """Descarga las fuentes que faltan."""
        syllabus = self._selected()
        if syllabus is None:
            return
        cancel = self.app.worker.cancel

        def fetch(reporter: Reporter) -> int:
            results = source_ops.download(syllabus, reporter, cancel=cancel)
            _show_results(reporter, results)
            return len(results)

        self._run("Descargando fuentes...", fetch)

    def check(self) -> None:
        """Busca versiones nuevas de todas las fuentes con URL."""
        syllabus = self._selected()
        if syllabus is None:
            return
        cancel = self.app.worker.cancel

        def look(reporter: Reporter) -> int:
            results, _ = source_ops.check(
                syllabus, reporter, check_all=True, cancel=cancel
            )
            _show_results(reporter, results)
            return len(results)

        self._run("Buscando versiones nuevas...", look)

    def index(self) -> None:
        """Indexa las fuentes nuevas del temario."""
        syllabus = self._selected()
        if syllabus is None:
            return
        station, cancel = self.app.station, self.app.worker.cancel

        def run(reporter: Reporter) -> int:
            count = knowledge_ops.index(station, syllabus, reporter, cancel=cancel)
            message = f"{count} fuentes indexadas." if count else "Nada que indexar."
            reporter.show([ok(message)])
            return count

        self._run("Indexando...", run)

    def reindex(self) -> None:
        """Reindexa las KB del temario con fuentes cambiadas o retiradas."""
        data = self._data.get(self._current or "")
        if data is None:
            self._selected()
            return
        _, stale = actions_needed(data.statuses)
        if not stale:
            messagebox.showinfo(
                "Atril", "No hay nada que reindexar en este temario.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Atril",
            f"Se reindexará {', '.join(stale)}. Puede tardar y DeepTutor se "
            "reiniciará si hace falta. ¿Continuar?",
            parent=self,
        ):
            return
        station, cancel = self.app.station, self.app.worker.cancel
        syllabus = data.syllabus
        kbs = [kb for kb in syllabus.knowledge_bases if kb.id in stale]

        def run(reporter: Reporter) -> int:
            for kb in kbs:
                message = knowledge_ops.reindex(station, syllabus, kb, reporter, cancel)
                reporter.show([ok(message)])
            return len(kbs)

        self._run("Reindexando...", run)

    def open_folder(self) -> None:
        """Abre la carpeta del temario elegido (o la de temarios)."""
        data = self._data.get(self._current or "")
        folder = data.syllabus.root if data else self.app.station.syllabi_dir
        webbrowser.open(folder.as_uri())

    # --- auxiliares -------------------------------------------------------------

    def _run(self, text: str, task: Callable[[Reporter], int], hint: str = "") -> None:
        """Lanza una acción del temario y, al acabar, vuelve a leer su estado."""

        def done(count: int) -> None:
            if hint and count:
                self.app.log(Level.INFO, hint)
            self.refresh()

        self.app.run(text, task, done)

    def _ask_kb(self, syllabus: Syllabus) -> str | None:
        """KB de destino: la única o la que elija el usuario."""
        ids = [kb.id for kb in syllabus.knowledge_bases]
        if len(ids) == 1:
            return ids[0]
        return ask_choice(self, "Base de conocimiento", "¿En qué KB va?", ids)


def ask_choice(
    parent: tk.Misc, title: str, prompt: str, options: list[str]
) -> str | None:
    """Diálogo modal con una lista desplegable; ``None`` si se cancela."""
    dialog = tk.Toplevel(parent, background=style.CARD, padx=18, pady=14)
    dialog.title(title)
    dialog.transient(parent.winfo_toplevel())
    dialog.resizable(False, False)
    style.label(dialog, prompt, background=style.CARD).grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    choice = tk.StringVar(dialog, options[0] if options else "")
    ttk.Combobox(
        dialog, textvariable=choice, values=options, state="readonly", width=32
    ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=10)
    result: list[str] = []

    def accept() -> None:
        result.append(choice.get())
        dialog.destroy()

    ttk.Button(dialog, text="Aceptar", style="Accent.TButton", command=accept).grid(
        row=2, column=0, sticky="e", padx=(0, 6)
    )
    ttk.Button(dialog, text="Cancelar", command=dialog.destroy).grid(
        row=2, column=1, sticky="w"
    )
    dialog.grab_set()
    dialog.wait_window()
    return result[0] if result else None


_OUTCOME_LEVELS = {
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


def _show_results(reporter: Reporter, results: list[Result]) -> None:
    """Resultado de cada fuente en la actividad."""
    reporter.show(
        [
            Finding(
                _OUTCOME_LEVELS[r.outcome],
                f"{r.source.id}: {r.outcome.value}"
                + (f" ({r.detail})" if r.detail else ""),
            )
            for r in results
        ]
    )
