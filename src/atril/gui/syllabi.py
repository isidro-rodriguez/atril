"""Apartado Temarios: elegir, crear, renombrar y borrar temarios, e indexar sus KB.

El temario elegido es el mismo en Temarios y Biblioteca y se recuerda para la
próxima vez (:meth:`atril.gui.app.App.choose_syllabus`).
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from atril.checks import ok
from atril.config import Syllabus
from atril.gui import style
from atril.gui.desktop import open_path
from atril.gui.dialogs import ask_text, ask_yes_no, confirm_delete, show_message
from atril.gui.model import (
    SyllabusData,
    actions_needed,
    choose_syllabus,
    load_all,
    size_label,
)
from atril.knowledge import PlanState
from atril.ops import Reporter
from atril.ops import knowledge as knowledge_ops
from atril.ops import syllabus as syllabus_ops
from atril.ops.knowledge import RUN_LABELS

if TYPE_CHECKING:
    from atril.gui.app import App


class SyllabusPicker(tk.Frame):
    """Desplegable de temarios, compartido por Temarios y Biblioteca."""

    def __init__(
        self, parent: tk.Misc, app: "App", on_change: Callable[[], None]
    ) -> None:
        """Construye la etiqueta y el desplegable."""
        super().__init__(parent, background=style.CARD)
        self.app = app
        self._on_change = on_change
        self._ids: list[str] = []
        style.label(self, "Temario", font=style.STRONG).grid(
            row=0, column=0, padx=(0, 10)
        )
        self._choice = tk.StringVar(self)
        self.combo = ttk.Combobox(
            self, textvariable=self._choice, state="readonly", width=34
        )
        self.combo.grid(row=0, column=1)
        self.combo.bind("<<ComboboxSelected>>", self._changed)

    def fill(self, data: list[SyllabusData]) -> str | None:
        """Pone los temarios y elige el activo; devuelve su id."""
        self._ids = [item.syllabus.id for item in data]
        self.combo.configure(values=[item.syllabus.name for item in data])
        current = choose_syllabus(self._ids, self.app.syllabus_id)
        self.app.choose_syllabus(current)
        self.combo.state(["!disabled"] if data else ["disabled"])
        if current is None:
            self._choice.set("Ningún temario")
        else:
            self.combo.current(self._ids.index(current))
        return current

    def _changed(self, _: object) -> None:
        """El usuario elige otro temario."""
        index = self.combo.current()
        if 0 <= index < len(self._ids):
            self.app.choose_syllabus(self._ids[index])
            self._on_change()


class SyllabiView(tk.Frame):
    """Cabecera con el temario elegido y, debajo, sus KB y acciones."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la cabecera y el detalle."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._data: dict[str, SyllabusData] = {}
        self._shown: str | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_header().grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._build_detail().grid(row=1, column=0, sticky="nsew")

    # --- construcción -----------------------------------------------------------

    def _build_header(self) -> ttk.Frame:
        """Desplegable de temarios y botones para crear y borrar."""
        card = style.card(self)
        card.columnconfigure(1, weight=1)
        self._picker = SyllabusPicker(card, self.app, self._show_detail)
        self._picker.grid(row=0, column=0, sticky="w")
        self.app.action(
            ttk.Button(
                card,
                text="Nuevo temario",
                style="Accent.TButton",
                command=self.new_syllabus,
            )
        ).grid(row=0, column=2, padx=(0, 8))
        self._delete = self.app.action(
            ttk.Button(card, text="Borrar temario", command=self.delete)
        )
        self._delete.grid(row=0, column=3)
        return card

    def _build_detail(self) -> ttk.Frame:
        """Tarjeta del temario: KB, pendientes y acciones."""
        card = style.card(self)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        self._title = style.label(
            card, "Crea un temario para empezar", font=style.TITLE
        )
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = style.label(card, "", color=style.MUTED, font=style.SMALL)
        self._subtitle.grid(row=1, column=0, sticky="w", pady=(0, 12))

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="w", pady=(0, 12))
        self._buttons: dict[str, ttk.Button] = {}
        for column, (text, command) in enumerate(
            (
                ("Indexar", self.index),
                ("Reindexar", self.reindex),
                ("Renombrar…", self.rename),
            )
        ):
            button = self.app.action(ttk.Button(tools, text=text, command=command))
            button.grid(row=0, column=column, padx=(0, 8))
            self._buttons[text] = button
        self.app.cancel_button(
            ttk.Button(tools, text="Cancelar", command=self.app.cancel)
        ).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(tools, text="Abrir carpeta", command=self.open_folder).grid(
            row=0, column=4
        )

        columns = ("kb", "fuentes", "indexadas", "pendientes", "deeptutor")
        self._kbs = ttk.Treeview(card, columns=columns, show="headings", height=5)
        for column, (title, width, stretch) in zip(
            columns,
            (
                ("Base de conocimiento", 220, True),
                ("Fuentes", 90, False),
                ("Indexadas", 100, False),
                ("Pendientes", 110, False),
                ("Último indexado", 150, False),
            ),
            strict=True,
        ):
            self._kbs.heading(column, text=title, anchor="w")
            self._kbs.column(
                column,
                width=round(width * style.scale(self)),
                anchor="w",
                stretch=stretch,
            )
        self._kbs.grid(row=3, column=0, sticky="nsew")
        self._pending = style.label(card, "", color=style.MUTED, wraplength=700)
        self._pending.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        return card

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Vuelve a leer los temarios y su estado en segundo plano."""
        station = self.app.station
        return self.app.run(
            "Leyendo temarios...",
            lambda reporter: load_all(station),
            self._show,
            quiet=True,
        )

    def follow_syllabus(self) -> None:
        """Muestra el temario activo si se eligió en otro apartado."""
        if self._data and self._shown != self.app.syllabus_id:
            self._show(list(self._data.values()))

    def _show(self, data: list[SyllabusData]) -> None:
        """Rellena el desplegable y el detalle del temario activo."""
        self._data = {item.syllabus.id: item for item in data}
        self._picker.fill(data)
        self._show_detail()

    def _show_detail(self) -> None:
        """KB del temario elegido, con sus recuentos y el último indexado."""
        self._kbs.delete(*self._kbs.get_children())
        self._shown = self.app.syllabus_id
        data = self._data.get(self._shown or "")
        for button in (*self._buttons.values(), self._delete):
            button.state(["!disabled"] if data else ["disabled"])
        if data is None:
            self._title.configure(text="Crea un temario para empezar")
            self._subtitle.configure(text="Pulsa «Nuevo temario».")
            self._pending.configure(text="")
            return
        self._title.configure(text=data.syllabus.name)
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
                values=style.cells(
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
        data = self._data.get(self.app.syllabus_id or "")
        if data is None:
            show_message(self, "Temarios", "Crea antes un temario.")
        return data

    # --- acciones ---------------------------------------------------------------

    def new_syllabus(self) -> None:
        """Crea un temario a partir de su nombre y lo deja elegido."""
        name = ask_text(self, "Nuevo temario", "Nombre del temario:")
        if not name:
            return
        station = self.app.station

        def created(syllabus: Syllabus) -> None:
            self.app.choose_syllabus(syllabus.id)
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
        """Borra el temario para siempre, tras dos confirmaciones."""
        data = self._selected()
        if data is None:
            return
        syllabus = data.syllabus
        found = syllabus_ops.contents(syllabus)
        kbs = ", ".join(found.knowledge_bases) or "ninguna"
        summary = (
            f"{found.files} ficheros ({size_label(found.size)}) y sus bases de "
            f"conocimiento ({kbs})"
        )
        if not confirm_delete(
            self, syllabus.name, summary, lambda: open_path(syllabus.root)
        ):
            return
        station = self.app.station

        def run(reporter: Reporter) -> None:
            syllabus_ops.delete(station, syllabus, reporter)
            reporter.show([ok(f"Temario «{syllabus.name}» borrado.")])

        self.app.choose_syllabus(None)
        self.app.run(
            "Borrando el temario...",
            run,
            lambda _: self.refresh(),
            title="Borrar temario",
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
            show_message(
                self, "Reindexar", "No hay nada que reindexar en este temario."
            )
            return
        if not ask_yes_no(
            self,
            "Reindexar",
            f"Se reindexará {', '.join(stale)}. Puede tardar y DeepTutor se "
            "reiniciará si hace falta.",
            "Reindexar",
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
        data = self._data.get(self.app.syllabus_id or "")
        open_path(data.syllabus.root if data else self.app.station.syllabi_dir)
