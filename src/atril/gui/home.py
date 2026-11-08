"""Apartado Inicio: estado general, accesos rápidos y temarios recientes."""

import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from tkinter import ttk
from typing import TYPE_CHECKING

from atril import backup
from atril.config import load_syllabi
from atril.config.station import Station
from atril.gui import style
from atril.gui.activity import when_label
from atril.gui.model import Row, ago_label, archive_label, overall, summarize
from atril.gui.syllabi import SyllabiView
from atril.gui.widgets import QuickTile
from atril.ops import Reporter, service
from atril.ops import syllabus as syllabus_ops
from atril.ops.service import Section

if TYPE_CHECKING:
    from atril.gui.app import App

RECENT = 4
"""Temarios recientes que se muestran."""


@dataclass(frozen=True, slots=True)
class HomeData:
    """Lo que necesita Inicio, leído en segundo plano."""

    sections: list[Section]
    last_backup: str | None
    """Fecha de la última copia completa, ya en texto."""
    recent: list[tuple[str, str, str]]
    """Temarios recientes: id, nombre y antigüedad."""


def load_home(station: Station, reporter: Reporter) -> HomeData:
    """Estado de servicios, última copia y temarios recientes."""
    sections = service.status(station, reporter)
    stamps = [
        archive.stamp
        for folder in station.backup.destinations
        if backup.is_reachable(folder)
        for archive in backup.archives(folder)
    ]
    last = archive_label(max(stamps)) if stamps else None
    try:
        syllabi, _ = load_syllabi(station.syllabi_dir)
    except Exception:
        syllabi = []
    now = time.time()
    recent = [
        (syllabus.id, syllabus.name, ago_label(modified, now))
        for syllabus, modified in syllabus_ops.recent(syllabi)[:RECENT]
    ]
    return HomeData(sections, last, recent)


class HomeView(tk.Frame):
    """Estado general, accesos rápidos y temarios modificados recientemente."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las tres tarjetas."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_status().grid(row=0, column=0, sticky="ew")
        self._build_quick().grid(row=1, column=0, sticky="ew", pady=16)
        self._build_recent().grid(row=2, column=0, sticky="nsew")

    def _build_status(self) -> tk.Frame | ttk.Frame:
        """Tarjeta de estado general: icono, titular, servicios y fechas."""
        card = style.card(self, "Estado general")
        card.columnconfigure(1, weight=1)
        self._icon = tk.Label(card, background=style.CARD)
        self._icon.grid(row=1, column=0, rowspan=2, sticky="nw", padx=(0, 16))
        self._headline = style.label(card, "Comprobando…", font=style.TITLE)
        self._headline.grid(row=1, column=1, sticky="sw")
        self._sentence = style.label(card, "", color=style.MUTED)
        self._sentence.grid(row=2, column=1, sticky="nw")
        self._rows = tk.Frame(card, background=style.CARD)
        self._rows.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self._rows.columnconfigure(2, weight=1)

        side = tk.Frame(card, background=style.CARD)
        side.grid(row=1, column=2, rowspan=3, sticky="ne", padx=(24, 0))
        style.label(side, "Última actividad", font=style.SMALL, color=style.MUTED).grid(
            row=0, column=0, sticky="w"
        )
        self._last_activity = style.label(side, "—", font=style.STRONG)
        self._last_activity.grid(row=1, column=0, sticky="w", pady=(0, 10))
        style.label(side, "Última copia", font=style.SMALL, color=style.MUTED).grid(
            row=2, column=0, sticky="w"
        )
        self._last_backup = style.label(side, "—", font=style.STRONG)
        self._last_backup.grid(row=3, column=0, sticky="w")
        return card

    def _build_quick(self) -> tk.Frame | ttk.Frame:
        """Accesos rápidos en baldosas."""
        card = style.card(self, "Accesos rápidos")
        tiles = (
            ("book-open-acc", "Estudiar", "Abrir DeepTutor", self.open_deeptutor),
            ("circle-plus-acc", "Crear", "Nuevo temario", self._new_syllabus),
            (
                "folder-open-acc",
                "Biblioteca",
                "Consultar materiales",
                lambda: self.app.show_view("Biblioteca"),
            ),
            (
                "wrench-acc",
                "Ajustes",
                "Copias e indexado",
                lambda: self.app.show_view("Ajustes"),
            ),
        )
        for column, (icon, title, subtitle, command) in enumerate(tiles):
            card.columnconfigure(column, weight=1, uniform="tiles")
            tile = QuickTile(card, icon, title, subtitle, command)
            tile.grid(
                row=1, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0)
            )
        return card

    def _build_recent(self) -> tk.Frame | ttk.Frame:
        """Temarios modificados recientemente."""
        card = style.card(self)
        card.columnconfigure(0, weight=1)
        head = tk.Frame(card, background=style.CARD)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        head.columnconfigure(0, weight=1)
        style.label(head, "Modificados recientemente", font=style.SUBTITLE).grid(
            row=0, column=0, sticky="w"
        )
        more = style.label(head, "Ver todos", font=style.STRONG, color=style.ACCENT)
        more.configure(cursor="hand2")
        more.grid(row=0, column=1)
        more.bind("<Button-1>", lambda _: self.app.show_view("Temarios"))
        self._recent = tk.Frame(card, background=style.CARD)
        self._recent.grid(row=1, column=0, sticky="nsew")
        self._recent.columnconfigure(1, weight=1)
        return card

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> None:
        """Comprueba el estado de la estación en segundo plano."""
        station = self.app.station
        self.app.run(
            "Comprobando el estado...",
            lambda reporter: load_home(station, reporter),
            self._show,
            quiet=True,
        )
        self._show_last_activity()

    def _show(self, data: HomeData) -> None:
        """Pinta estado, fechas y recientes."""
        rows = summarize(data.sections)
        level, headline, sentence = overall(rows)
        self.app.set_overall(level)
        self._icon.configure(image=style.icon(self, style.LEVEL_ICONS[level], 40))
        self._headline.configure(text=headline, foreground=style.LEVEL_COLORS[level])
        self._sentence.configure(text=sentence)
        for widget in self._rows.winfo_children():
            widget.destroy()
        for index, row in enumerate(rows):
            self._status_row(index, row)
        self._last_backup.configure(text=data.last_backup or "Ninguna todavía")
        self._show_last_activity()
        for widget in self._recent.winfo_children():
            widget.destroy()
        if not data.recent:
            style.label(
                self._recent, "Aún no hay temarios: crea uno.", color=style.MUTED
            ).grid(row=0, column=0, columnspan=3, sticky="w")
        for index, (syllabus_id, name, ago) in enumerate(data.recent):
            self._recent_row(index, syllabus_id, name, ago)

    def _show_last_activity(self) -> None:
        """Fecha de la última operación terminada."""
        done = [event for event in self.app.activity.events if not event.running]
        self._last_activity.configure(text=when_label(done[0].when) if done else "—")

    def _status_row(self, index: int, row: Row) -> None:
        """Un servicio: icono de nivel, nombre y estado."""
        tk.Label(
            self._rows,
            image=style.icon(self, style.LEVEL_ICONS[row.level], 18),
            background=style.CARD,
        ).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=2)
        style.label(self._rows, row.title, font=style.STRONG).grid(
            row=index, column=1, sticky="w", padx=(0, 12), pady=2
        )
        style.label(self._rows, row.message, wraplength=520).grid(
            row=index, column=2, sticky="w", pady=2
        )

    def _recent_row(self, index: int, syllabus_id: str, name: str, ago: str) -> None:
        """Un temario reciente; al pulsarlo se abre en Temarios."""
        widgets = (
            tk.Label(
                self._recent,
                image=style.icon(self, "book-open-acc", 18),
                background=style.CARD,
            ),
            style.label(self._recent, name),
            style.label(self._recent, ago, color=style.MUTED, font=style.SMALL),
        )
        for column, widget in enumerate(widgets):
            widget.configure(cursor="hand2")
            widget.grid(row=index, column=column, sticky="w", padx=(0, 10), pady=4)
            widget.bind("<Button-1>", lambda _, s=syllabus_id: self._open(s))

    # --- acciones ---------------------------------------------------------------

    def open_deeptutor(self) -> None:
        """Arranca DeepTutor si hace falta y lo abre en el navegador."""
        station = self.app.station

        def opened(url: str) -> None:
            webbrowser.open(url)
            self.refresh()

        self.app.run(
            "Abriendo DeepTutor (la primera vez tarda unos minutos)...",
            lambda reporter: service.open_url(station, reporter),
            opened,
            title="Abrir DeepTutor",
        )

    def _new_syllabus(self) -> None:
        """Va a Temarios y abre «Nuevo temario»."""
        self.app.show_view("Temarios")
        view = self.app.views["Temarios"]
        if isinstance(view, SyllabiView):
            view.new_syllabus()

    def _open(self, syllabus_id: str) -> None:
        """Abre un temario en el apartado Temarios."""
        self.app.show_view("Temarios")
        view = self.app.views["Temarios"]
        if isinstance(view, SyllabiView):
            view.select(syllabus_id)
