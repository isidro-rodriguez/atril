"""Apartado Inicio: estado de la estación y accesos rápidos."""

import time
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import TYPE_CHECKING

from atril.checks import Level
from atril.gui import style
from atril.gui.model import Row, overall, summarize
from atril.ops import Reporter, service
from atril.ops.service import Section

if TYPE_CHECKING:
    from atril.gui.app import App


class HomeView(tk.Frame):
    """Estado general (DeepTutor, Ollama, copias) y accesos a DeepTutor."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las tarjetas de estado y de accesos rápidos."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        status = style.card(self, "Estado general")
        status.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        status.columnconfigure(0, weight=1)
        self._overall = style.label(
            status, "Comprobando…", background=style.CARD, font=style.STRONG
        )
        self._overall.grid(row=1, column=0, sticky="w")
        self._checked = style.label(
            status, background=style.CARD, font=style.CAPTION, color=style.MUTED
        )
        self._checked.grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._rows = tk.Frame(status, background=style.CARD)
        self._rows.grid(row=3, column=0, sticky="new")
        self._rows.columnconfigure(2, weight=1)

        actions = style.card(self, "Accesos rápidos")
        actions.grid(row=0, column=1, sticky="nsew")
        actions.columnconfigure(0, weight=1)
        buttons = [
            ttk.Button(
                actions,
                text="Abrir DeepTutor",
                style="Accent.TButton",
                command=self.open_deeptutor,
            ),
            ttk.Button(actions, text="Parar DeepTutor", command=self.stop_deeptutor),
            ttk.Button(actions, text="Comprobar estado", command=self.refresh),
        ]
        for row, button in enumerate(buttons, start=1):
            app.action(button).grid(row=row, column=0, sticky="ew", pady=4)
        ttk.Button(
            actions,
            text="Abrir carpeta de la estación",
            command=lambda: webbrowser.open(app.station.root.as_uri()),
        ).grid(row=len(buttons) + 1, column=0, sticky="ew", pady=4)

    def refresh(self) -> None:
        """Comprueba el estado de la estación en segundo plano."""
        station = self.app.station
        self.app.run(
            "Comprobando el estado...",
            lambda reporter: service.status(station, reporter),
            self._show_status,
            quiet=True,
        )

    def open_deeptutor(self) -> None:
        """Arranca DeepTutor si hace falta y lo abre en el navegador."""
        station = self.app.station

        def opened(url: str) -> None:
            self.app.log(Level.OK, f"DeepTutor listo: {url}")
            webbrowser.open(url)
            self.refresh()

        self.app.run(
            "Abriendo DeepTutor (la primera vez tarda unos minutos)...",
            lambda reporter: service.open_url(station, reporter),
            opened,
        )

    def stop_deeptutor(self) -> None:
        """Detiene DeepTutor y sus procesos de la estación."""
        station = self.app.station

        def stop(reporter: Reporter) -> None:
            service.stop(service.installed(station), reporter)

        def stopped(_: None) -> None:
            self.app.log(Level.OK, "DeepTutor detenido.")
            self.refresh()

        self.app.run("Deteniendo DeepTutor...", stop, stopped)

    def _show_status(self, sections: list[Section]) -> None:
        """Pinta el resumen del estado."""
        rows = summarize(sections)
        level, text = overall(rows)
        self._overall.configure(
            text=f"{style.LEVEL_SYMBOLS[level]}  {text}",
            foreground=style.LEVEL_COLORS[level],
        )
        self._checked.configure(text=f"Comprobado a las {time.strftime('%H:%M')}")
        for widget in self._rows.winfo_children():
            widget.destroy()
        for index, row in enumerate(rows):
            self._status_row(index, row)

    def _status_row(self, index: int, row: Row) -> None:
        """Una fila: símbolo de nivel, sección y mensaje."""
        symbol, color = style.LEVEL_SYMBOLS[row.level], style.LEVEL_COLORS[row.level]
        cells = (
            (symbol, style.STRONG, color),
            (row.title, style.STRONG, style.TEXT),
            (row.message, style.BODY, style.TEXT),
        )
        for column, (text, font, fg) in enumerate(cells):
            style.label(
                self._rows,
                text,
                background=style.CARD,
                font=font,
                color=fg,
                wraplength=440 if column == 2 else 0,
            ).grid(row=index, column=column, sticky="nw", padx=(0, 10), pady=3)
