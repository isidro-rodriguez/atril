"""Apartado Ajustes: copias de seguridad y ritmo del indexado, sin tocar TOML."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from atril.config.station import ARCHIVE_FORMATS
from atril.errors import AtrilError
from atril.gui import style
from atril.gui.desktop import open_path
from atril.ops import settings as settings_ops

if TYPE_CHECKING:
    from atril.gui.app import App

INDEXING_HELP = {
    "hilos": "Hilos de cálculo al indexar (0 = los que decida DeepTutor). Menos "
    "hilos dejan el ordenador más libre.",
    "lote_embedding": "Fragmentos que se envían juntos a Ollama. Bájalo si el "
    "indexado falla por falta de memoria.",
    "pausa_embedding": "Milisegundos de pausa entre lotes. Súbelo si el ordenador "
    "se calienta o va lento mientras indexa.",
}
"""Explicación llana de cada ajuste del indexado."""


class SettingsView(tk.Frame):
    """Destinos y retención de copias, y ritmo del indexado."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las dos tarjetas y los botones Guardar y Descartar."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self.columnconfigure(0, weight=1)
        self._format = tk.StringVar(master=self)
        self._keep = tk.IntVar(master=self)
        self._indexing = {key: tk.IntVar(master=self) for key in INDEXING_HELP}
        self._build_backup().grid(row=0, column=0, sticky="ew")
        self._build_indexing().grid(row=1, column=0, sticky="ew", pady=16)
        bar = tk.Frame(self, background=style.PAGE)
        bar.grid(row=2, column=0, sticky="ew")
        app.action(
            ttk.Button(bar, text="Guardar", style="Accent.TButton", command=self.save)
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(bar, text="Descartar cambios", command=self.refresh).grid(
            row=0, column=1, padx=(0, 24)
        )
        ttk.Button(bar, text="Abrir atril.toml", command=self.open_config).grid(
            row=0, column=2
        )
        self._note = style.label(bar, "", background=style.PAGE, color=style.MUTED)
        self._note.grid(row=0, column=3, padx=(16, 0))

    def _build_backup(self) -> ttk.Frame:
        """Tarjeta de copias: destinos, formato y cuántas conservar."""
        card = style.card(self, "Copias de seguridad")
        card.columnconfigure(1, weight=1)
        style.label(card, "Destinos", font=style.STRONG).grid(
            row=1, column=0, sticky="nw", padx=(0, 16)
        )
        self._destinations = tk.Listbox(
            card,
            height=4,
            font=style.BODY,
            activestyle="none",
            relief="flat",
            highlightthickness=1,
            highlightbackground=style.BORDER,
            background=style.CARD,
            foreground=style.TEXT,
        )
        self._destinations.grid(row=1, column=1, sticky="ew")
        buttons = tk.Frame(card, background=style.CARD)
        buttons.grid(row=1, column=2, sticky="n", padx=(8, 0))
        ttk.Button(buttons, text="Añadir carpeta…", command=self.add_folder).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(buttons, text="Quitar", command=self.remove_folder).grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )
        style.label(
            card,
            "Usa una carpeta fuera de la estación, mejor en otro disco o en una "
            "carpeta sincronizada (OneDrive...). Un disco desconectado se salta.",
            color=style.MUTED,
            font=style.SMALL,
            wraplength=640,
        ).grid(row=2, column=1, columnspan=2, sticky="w", pady=(4, 12))
        style.label(card, "Formato", font=style.STRONG).grid(
            row=3, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Combobox(
            card,
            textvariable=self._format,
            values=ARCHIVE_FORMATS,
            state="readonly",
            width=10,
        ).grid(row=3, column=1, sticky="w")
        style.label(card, "Conservar", font=style.STRONG).grid(
            row=4, column=0, sticky="w", padx=(0, 16), pady=(8, 0)
        )
        ttk.Spinbox(card, from_=1, to=99, textvariable=self._keep, width=6).grid(
            row=4, column=1, sticky="w", pady=(8, 0)
        )
        style.label(
            card,
            "zip es más rápido; tar.xz ocupa menos. Se borran las copias más "
            "antiguas por encima de «Conservar».",
            color=style.MUTED,
            font=style.SMALL,
        ).grid(row=5, column=1, columnspan=2, sticky="w", pady=(4, 0))
        return card

    def _build_indexing(self) -> ttk.Frame:
        """Tarjeta de indexado: hilos, lote y pausa, con su explicación."""
        card = style.card(self, "Indexado")
        card.columnconfigure(2, weight=1)
        titles = {
            "hilos": "Hilos",
            "lote_embedding": "Tamaño de lote",
            "pausa_embedding": "Pausa (ms)",
        }
        for row, (key, text) in enumerate(INDEXING_HELP.items(), start=1):
            style.label(card, titles[key], font=style.STRONG).grid(
                row=row, column=0, sticky="w", padx=(0, 16), pady=4
            )
            minimum = 1 if key == "lote_embedding" else 0
            ttk.Spinbox(
                card,
                from_=minimum,
                to=10000,
                textvariable=self._indexing[key],
                width=8,
            ).grid(row=row, column=1, sticky="w", pady=4)
            style.label(
                card, text, color=style.MUTED, font=style.SMALL, wraplength=560
            ).grid(row=row, column=2, sticky="w", padx=(16, 0))
        return card

    def refresh(self) -> bool:
        """Carga los valores actuales de la estación."""
        station = self.app.station
        self._destinations.delete(0, "end")
        for folder in station.backup.destinations:
            self._destinations.insert("end", str(folder))
        self._format.set(station.backup.archive_format)
        self._keep.set(station.backup.keep)
        indexing = station.indexing
        self._indexing["hilos"].set(indexing.threads)
        self._indexing["lote_embedding"].set(indexing.batch_size)
        self._indexing["pausa_embedding"].set(indexing.pause_ms)
        self._note.configure(text="")
        return True

    def add_folder(self) -> None:
        """Añade un destino elegido con el explorador."""
        folder = filedialog.askdirectory(parent=self, title="Carpeta para las copias")
        if folder and str(Path(folder)) not in self._destinations.get(0, "end"):
            self._destinations.insert("end", str(Path(folder)))

    def remove_folder(self) -> None:
        """Quita el destino seleccionado."""
        for index in reversed(self._destinations.curselection()):
            self._destinations.delete(index)

    def save(self) -> None:
        """Valida y guarda en ``atril.toml``; un valor erróneo no se guarda."""
        try:
            changes = {
                "backup": {
                    "destinos": list(self._destinations.get(0, "end")),
                    "formato": self._format.get(),
                    "conservar": self._keep.get(),
                },
                "indexado": {key: var.get() for key, var in self._indexing.items()},
            }
        except tk.TclError:
            messagebox.showerror("Atril", "Escribe números enteros.", parent=self)
            return
        try:
            self.app.station = settings_ops.update(self.app.station, changes)
        except AtrilError as exc:
            messagebox.showerror("Atril", f"No se ha guardado: {exc}", parent=self)
            return
        self._note.configure(text="Guardado.")

    def open_config(self) -> None:
        """Abre ``atril.toml`` (ajustes avanzados)."""
        open_path(self.app.station.config_file)
