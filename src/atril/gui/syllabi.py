"""Apartado Temarios: crear, renombrar y eliminar temarios, y mantener sus KB."""

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from atril.checks import ok
from atril.config import Syllabus
from atril.gui import style
from atril.gui.desktop import open_path
from atril.gui.dialogs import ask_text, confirm_delete
from atril.gui.library import LibraryView
from atril.gui.model import SyllabusData, actions_needed, load_all
from atril.knowledge import PlanState
from atril.ops import Reporter
from atril.ops import knowledge as knowledge_ops
from atril.ops import syllabus as syllabus_ops
from atril.ops.knowledge import RUN_LABELS

if TYPE_CHECKING:
    from atril.gui.app import App


class SyllabiView(tk.Frame):
    """Lista de temarios y, del elegido, sus KB y acciones."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la lista y el detalle."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._data: dict[str, SyllabusData] = {}
        self._current: str | None = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_list().grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self._build_detail().grid(row=0, column=1, sticky="nsew")

    # --- construcción -----------------------------------------------------------

    def _build_list(self) -> tk.Frame | ttk.Frame:
        """Tarjeta con los temarios y el botón para crear uno."""
        card = style.card(self, "Temarios")
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)
        self._list = ttk.Treeview(
            card, columns=("nombre",), show="", selectmode="browse", height=10
        )
        self._list.column("nombre", width=round(230 * style.scale(self)))
        self._list.grid(row=1, column=0, sticky="nsew")
        self._list.bind("<<TreeviewSelect>>", self._on_select)
        self.app.action(
            ttk.Button(
                card,
                text="Nuevo temario…",
                style="Accent.TButton",
                command=self.new_syllabus,
            )
        ).grid(row=2, column=0, sticky="ew", pady=(12, 0))
        return card

    def _build_detail(self) -> tk.Frame | ttk.Frame:
        """Tarjeta con el temario elegido: KB, pendientes y acciones."""
        card = style.card(self)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        self._title = style.label(card, "Elige o crea un temario", font=style.TITLE)
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = style.label(card, "", color=style.MUTED, font=style.SMALL)
        self._subtitle.grid(row=1, column=0, sticky="w", pady=(0, 12))

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="w", pady=(0, 12))
        self._buttons: dict[str, ttk.Button] = {}
        actions: list[tuple[str, Callable[[], None]]] = [
            ("Indexar", self.index),
            ("Reindexar", self.reindex),
            ("Renombrar…", self.rename),
            ("Eliminar…", self.delete),
        ]
        for column, (text, command) in enumerate(actions):
            button = self.app.action(ttk.Button(tools, text=text, command=command))
            button.grid(row=0, column=column, padx=(0, 8))
            self._buttons[text] = button
        self.app.cancel_button(
            ttk.Button(tools, text="Cancelar", command=self.app.cancel)
        ).grid(row=0, column=len(actions), padx=(0, 8))
        ttk.Button(tools, text="Abrir carpeta", command=self.open_folder).grid(
            row=0, column=len(actions) + 1
        )

        columns = ("kb", "fuentes", "indexadas", "pendientes", "deeptutor")
        self._kbs = ttk.Treeview(card, columns=columns, show="headings", height=5)
        for column, (title, width, anchor) in zip(
            columns,
            (
                ("Base de conocimiento", 220, "w"),
                ("Fuentes", 80, "e"),
                ("Indexadas", 90, "e"),
                ("Pendientes", 100, "e"),
                ("Último indexado", 150, "w"),
            ),
            strict=True,
        ):
            self._kbs.heading(column, text=title, anchor=anchor)
            self._kbs.column(
                column,
                width=round(width * style.scale(self)),
                anchor=anchor,
                stretch=column == "kb",
            )
        self._kbs.grid(row=3, column=0, sticky="nsew")
        self._pending = style.label(card, "", color=style.MUTED, wraplength=640)
        self._pending.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        more = style.label(card, "Ver sus fuentes en la Biblioteca", color=style.ACCENT)
        more.configure(cursor="hand2")
        more.grid(row=5, column=0, sticky="w", pady=(8, 0))
        more.bind("<Button-1>", lambda _: self._open_library())
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

    def select(self, syllabus_id: str) -> None:
        """Elige un temario (si aún no está cargado, al cargar)."""
        self._current = syllabus_id
        if syllabus_id in self._data:
            self._list.selection_set(syllabus_id)
            self._show_detail()

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
        """KB del temario elegido, con sus recuentos y el último indexado."""
        self._kbs.delete(*self._kbs.get_children())
        data = self._data.get(self._current or "")
        if data is None:
            self._title.configure(text="Elige o crea un temario")
            self._subtitle.configure(text="")
            self._pending.configure(text="")
            return
        syllabus = data.syllabus
        self._title.configure(text=syllabus.name)
        total = sum(len(status.items) for status in data.statuses)
        self._subtitle.configure(
            text=f"{len(data.statuses)} bases de conocimiento · {total} fuentes"
        )
        for status in data.statuses:
            pending = status.count(PlanState.NEW) + status.count(PlanState.CHANGED)
            run = status.run
            last = RUN_LABELS.get(run.state, run.state) if run else "Sin indexar"
            self._kbs.insert(
                "",
                "end",
                values=(
                    status.kb.id,
                    len(status.items),
                    status.count(PlanState.INDEXED),
                    pending,
                    last.capitalize(),
                ),
            )
        new, stale = actions_needed(data.statuses)
        hints = [finding.message for finding in data.pending]
        self._pending.configure(text="\n".join(hints) or "Todo indexado.")
        self._buttons["Indexar"].configure(style="Accent.TButton" if new else "TButton")
        self._buttons["Reindexar"].configure(
            style="Accent.TButton" if stale else "TButton"
        )

    def _selected(self) -> SyllabusData | None:
        """Temario elegido; si no hay, lo explica."""
        data = self._data.get(self._current or "")
        if data is None:
            messagebox.showinfo("Atril", "Elige antes un temario.", parent=self)
        return data

    # --- acciones ---------------------------------------------------------------

    def new_syllabus(self) -> None:
        """Crea un temario a partir de su nombre."""
        name = ask_text(self, "Nuevo temario", "Nombre del temario:")
        if not name:
            return
        station = self.app.station

        def created(syllabus: Syllabus) -> None:
            self._current = syllabus.id
            self.refresh()

        def create(reporter: Reporter) -> Syllabus:
            syllabus = syllabus_ops.create(station, name)
            reporter.show([ok(f"Temario «{syllabus.name}» creado.")])
            return syllabus

        self.app.run("Creando el temario...", create, created, title="Nuevo temario")

    def rename(self) -> None:
        """Cambia el nombre visible del temario elegido."""
        data = self._selected()
        if data is None:
            return
        name = ask_text(self, "Renombrar temario", "Nuevo nombre:", data.syllabus.name)
        if not name or name == data.syllabus.name:
            return

        def run(reporter: Reporter) -> None:
            renamed = syllabus_ops.rename(data.syllabus, name)
            reporter.show([ok(f"Ahora se llama «{renamed.name}».")])

        self.app.run(
            "Renombrando...", run, lambda _: self.refresh(), title="Renombrar temario"
        )

    def delete(self) -> None:
        """Mueve el temario a la papelera (y, si se pide, borra sus KB)."""
        data = self._selected()
        if data is None:
            return
        syllabus = data.syllabus
        kbs = [kb.id for kb in syllabus.knowledge_bases]
        delete_kbs = confirm_delete(self, syllabus.name, kbs)
        if delete_kbs is None:
            return
        station = self.app.station

        def run(reporter: Reporter) -> None:
            target = syllabus_ops.delete(
                station, syllabus, reporter, delete_kbs=delete_kbs
            )
            reporter.show(
                [ok(f"«{syllabus.name}» movido a la papelera ({target.name}).")]
            )

        self._current = None
        self.app.run(
            "Eliminando el temario...",
            run,
            lambda _: self.refresh(),
            title="Eliminar temario",
        )

    def index(self) -> None:
        """Indexa las fuentes nuevas del temario."""
        data = self._selected()
        if data is None:
            return
        station, cancel = self.app.station, self.app.worker.cancel
        syllabus = data.syllabus

        def run(reporter: Reporter) -> None:
            count = knowledge_ops.index(station, syllabus, reporter, cancel=cancel)
            message = f"{count} fuentes indexadas." if count else "Nada que indexar."
            reporter.show([ok(message)])

        self.app.run(
            "Indexando...",
            run,
            lambda _: self.refresh(),
            title=f"Indexar {syllabus.name}",
        )

    def reindex(self) -> None:
        """Reindexa las KB del temario con fuentes cambiadas o retiradas."""
        data = self._selected()
        if data is None:
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

        def run(reporter: Reporter) -> None:
            for kb in kbs:
                message = knowledge_ops.reindex(station, syllabus, kb, reporter, cancel)
                reporter.show([ok(message)])

        self.app.run(
            "Reindexando...",
            run,
            lambda _: self.refresh(),
            title=f"Reindexar {syllabus.name}",
        )

    def open_folder(self) -> None:
        """Abre la carpeta del temario elegido (o la de temarios)."""
        data = self._data.get(self._current or "")
        open_path(data.syllabus.root if data else self.app.station.syllabi_dir)

    def _open_library(self) -> None:
        """Muestra la Biblioteca filtrada por este temario."""
        self.app.show_view("Biblioteca")
        view = self.app.views["Biblioteca"]
        if self._current and isinstance(view, LibraryView):
            view.filter_syllabus(self._current)
