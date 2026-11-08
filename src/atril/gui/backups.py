"""Apartado Copias: hacer, comprobar y restaurar copias de seguridad."""

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from acodo.utils import parse_size

from atril.checks import Level, info, ok, warning
from atril.gui import style
from atril.gui.desktop import open_path
from atril.ops import Reporter
from atril.ops import backup as backup_ops
from atril.ops.backup import FolderReport, OtherRootError, Restored, RestorePlan

if TYPE_CHECKING:
    from pathlib import Path

    from atril.gui.app import App


class BackupsView(tk.Frame):
    """Copias de cada destino y acciones para hacerlas, comprobarlas y restaurarlas."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la tabla de copias y sus botones."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._paths: dict[str, Path] = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        card = style.card(self, "Copias de seguridad")
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        style.label(
            card,
            "Guardan atril.toml, data/ y temarios/ (sin app/). Las claves de API no "
            "viajan: tras restaurar hay que volver a escribirlas en DeepTutor.",
            background=style.CARD,
            color=style.MUTED,
            wraplength=760,
        ).grid(row=1, column=0, sticky="w")

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="w", pady=10)
        for column, (text, command, accent) in enumerate(
            (
                ("Hacer copia ahora", self.create, True),
                ("Comprobar copias", self.check, False),
                ("Restaurar…", self.restore, False),
            )
        ):
            button = ttk.Button(
                tools,
                text=text,
                command=command,
                style="Accent.TButton" if accent else "TButton",
            )
            app.action(button).grid(row=0, column=column, padx=(0, 6))
        app.cancel_button(ttk.Button(tools, text="Cancelar", command=app.cancel)).grid(
            row=0, column=3, padx=(0, 6)
        )
        ttk.Button(tools, text="Abrir destino", command=self.open_folder).grid(
            row=0, column=4
        )

        table = tk.Frame(card, background=style.CARD)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self._table = ttk.Treeview(
            table, columns=("copia", "tamano", "destino"), show="headings", height=10
        )
        self._table.heading("copia", text="Copia", anchor="w")
        self._table.heading("tamano", text="Tamaño", anchor="e")
        self._table.heading("destino", text="Destino", anchor="w")
        self._table.column("copia", width=240, anchor="w", stretch=False)
        self._table.column("tamano", width=100, anchor="e", stretch=False)
        self._table.column("destino", width=360, anchor="w")
        self._table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, command=self._table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._table.configure(yscrollcommand=scroll.set)

    def refresh(self) -> None:
        """Lista las copias de cada destino (sin verificarlas)."""
        station = self.app.station
        self.app.run(
            "Buscando copias...",
            lambda reporter: backup_ops.listing(station, reporter),
            self._show,
            quiet=True,
        )

    def _show(self, reports: list[FolderReport]) -> None:
        """Pinta los destinos con sus copias, de la más reciente a la más antigua."""
        self._table.delete(*self._table.get_children())
        self._paths.clear()
        for report in reports:
            folder = str(report.folder)
            if not report.archives:
                self._table.insert("", "end", values=("sin copias", "", folder))
            for archive in reversed(report.archives):
                values = (archive.path.name, parse_size(archive.size), folder)
                self._paths[self._table.insert("", "end", values=values)] = archive.path

    def create(self) -> None:
        """Hace una copia (para y vuelve a arrancar DeepTutor si estaba en marcha)."""
        station, cancel = self.app.station, self.app.worker.cancel

        def run(reporter: Reporter) -> None:
            created = backup_ops.create(station, reporter, cancel=cancel)
            size = parse_size(created.size)
            reporter.show([ok(f"Copia {created.archive.name} ({size}) terminada.")])

        self.app.run("Haciendo la copia...", run, lambda _: self.refresh())

    def check(self) -> None:
        """Verifica la copia más reciente de cada destino."""
        station = self.app.station

        def run(reporter: Reporter) -> list[FolderReport]:
            reports = backup_ops.check(station, reporter)
            for report in reports:
                reporter.show(report.findings)
            return reports

        self.app.run("Verificando copias...", run, self._show)

    def restore(self) -> None:
        """Restaura la copia elegida (o la más reciente), tras confirmarlo."""
        selected = [self._paths[i] for i in self._table.selection() if i in self._paths]
        archive = selected[0] if selected else None
        station = self.app.station
        self.app.run(
            "Preparando la restauración...",
            lambda reporter: backup_ops.plan_restore(station, reporter, archive),
            self._confirm_restore,
        )

    def _confirm_restore(self, plan: RestorePlan, other_root: bool = False) -> None:
        """Pide confirmación y restaura; ofrece aceptar una copia de otra ruta."""
        station = self.app.station
        if not other_root and not messagebox.askyesno(
            "Restaurar copia", plan.question(station), icon="warning", parent=self
        ):
            return

        def run(reporter: Reporter) -> Restored | OtherRootError:
            try:
                return backup_ops.restore(
                    station, plan, reporter, other_root=other_root
                )
            except OtherRootError as exc:
                return exc

        def done(result: Restored | OtherRootError) -> None:
            if isinstance(result, OtherRootError):
                if messagebox.askyesno(
                    "Restaurar copia",
                    f"{result}\n\n¿Restaurarla de todos modos en esta estación?",
                    icon="warning",
                    parent=self,
                ):
                    self._confirm_restore(plan, other_root=True)
                return
            self._restored(result)

        self.app.run("Restaurando...", run, done)

    def _restored(self, result: Restored) -> None:
        """Informa del resultado de la restauración."""
        findings = [
            ok(f"Restaurado: {', '.join(result.replaced)}."),
            info(f"Lo anterior está en {result.keep}; bórralo cuando compruebes todo."),
        ]
        if result.blanked_keys:
            findings.append(
                warning(
                    f"La copia no lleva las {result.blanked_keys} claves de API: "
                    "vuelve a escribirlas en la configuración de DeepTutor."
                )
            )
        for finding in findings:
            self.app.log(finding.level, finding.message)
        self.app.log(Level.INFO, "Comprueba el estado en Inicio.")
        self.refresh()

    def open_folder(self) -> None:
        """Abre el primer destino de copias."""
        destinations = self.app.station.backup.destinations
        if destinations and destinations[0].is_dir():
            open_path(destinations[0])
        else:
            messagebox.showinfo(
                "Atril", "El destino de copias no está accesible.", parent=self
            )
