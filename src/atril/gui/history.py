"""Apartado Actividad: las operaciones de la ventana y su detalle técnico."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from atril.checks import Level
from atril.gui import style
from atril.gui.activity import Event, when_label
from atril.gui.model import fold
from atril.gui.widgets import TableSorter

if TYPE_CHECKING:
    from atril.gui.app import App


class HistoryView(tk.Frame):
    """Lista de operaciones (la más reciente arriba) y el detalle de la elegida."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la lista y el panel de detalle."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._events: dict[str, Event] = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        card = style.card(self, "Actividad")
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=3)
        card.rowconfigure(2, weight=2)

        table = tk.Frame(card, background=style.CARD)
        table.grid(row=1, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("cuando", "operacion", "resultado")
        self._list = ttk.Treeview(table, columns=columns, show="headings", height=8)
        for column, title, width in zip(
            columns, ("Cuándo", "Operación", "Resultado"), (120, 200, 330), strict=True
        ):
            self._list.heading(column, text=title, anchor="w")
            self._list.column(
                column,
                width=round(width * style.scale(self)),
                stretch=column == "resultado",
            )
        style.tag_levels(self._list)
        self._sorter = TableSorter(self._list)
        self._list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, command=self._list.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        style.autoscroll(self._list, scroll)
        self._list.bind("<<TreeviewSelect>>", self._show_event)

        self._detail = tk.Text(
            card,
            height=6,
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
            self._detail.tag_configure(level.value, foreground=color)
        self._detail.grid(row=2, column=0, sticky="nsew", pady=(10, 0))

    def refresh(self) -> bool:
        """Repinta la lista desde la actividad en memoria (no lee nada)."""
        selected = self._list.selection()
        chosen = self._events.get(selected[0]) if selected else None
        current = chosen.id if chosen else None
        self._list.delete(*self._list.get_children())
        self._sorter.clear()
        self._events.clear()
        for event in self.app.activity.events:
            when = "Ahora" if event.running else when_label(event.when)
            item = self._list.insert(
                "",
                "end",
                values=style.cells(when, event.title, event.summary),
                tags=(event.level.value,),
            )
            self._events[item] = event
            moment = "9999" if event.running else event.when  # en curso: lo último
            self._sorter.add(item, (moment, fold(event.title), fold(event.summary)))
            if event.id == current:
                self._list.selection_set(item)
        self._sorter.apply()
        if not self._events:
            self._write([(Level.INFO, "Sin actividad todavía.")])
        elif not self._list.selection():
            self._write([(Level.INFO, "Elige una operación para ver su detalle.")])
        return True

    def _show_event(self, _: object = None) -> None:
        """Detalle técnico del evento elegido."""
        selected = self._list.selection()
        if not selected or selected[0] not in self._events:
            return
        event = self._events[selected[0]]
        lines = [(Level(value), message) for value, message in event.detail]
        self._write(lines or [(event.level, event.summary or event.title)])

    def _write(self, lines: list[tuple[Level, str]]) -> None:
        """Sustituye el detalle por ``lines`` con su símbolo de nivel."""
        self._detail.configure(state="normal")
        self._detail.delete("1.0", "end")
        for level, message in lines:
            self._detail.insert(
                "end", f"{style.LEVEL_SYMBOLS[level]} {message}\n", level.value
            )
        self._detail.configure(state="disabled")
