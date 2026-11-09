"""Apartado Backups: hacer, comprobar y restaurar copias de seguridad."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

from acodo.utils import parse_size

from atril.checks import Level, info, ok, warning
from atril.gui import style
from atril.gui.desktop import open_path
from atril.gui.dialogs import ask_yes_no, show_message
from atril.gui.model import archive_label, fold
from atril.gui.widgets import TableSorter
from atril.ops import Reporter
from atril.ops import backup as backup_ops
from atril.ops.backup import FolderReport, OtherRootError, Restored, RestorePlan

if TYPE_CHECKING:
    from atril.gui.app import App

PENDING = "Sin comprobar"
"""Estado de verificación hasta pulsar «Comprobar»."""


class BackupsView(tk.Frame):
    """Copias de cada destino y acciones para hacerlas, comprobarlas y restaurarlas."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye la tabla de copias y sus botones."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._paths: dict[str, Path] = {}
        self._verified: dict[Path, tuple[str, Level]] = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        card = style.card(self, "Backups")
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)
        style.label(
            card,
            "Backups de temarios, bases de conocimiento y ajustes.",
            color=style.MUTED,
            wraplength=760,
        ).grid(row=1, column=0, sticky="w")

        tools = tk.Frame(card, background=style.CARD)
        tools.grid(row=2, column=0, sticky="w", pady=12)
        for column, (text, command, accent) in enumerate(
            (
                ("Hacer backup", self.create, True),
                ("Comprobar", self.check, False),
                ("Restaurar…", self.restore, False),
            )
        ):
            button = ttk.Button(
                tools,
                text=text,
                command=command,
                style="Accent.TButton" if accent else "TButton",
            )
            app.action(button).grid(row=0, column=column, padx=(0, 8))
        app.cancel_button(ttk.Button(tools, text="Cancelar", command=app.cancel)).grid(
            row=0, column=3, padx=(0, 8)
        )
        ttk.Button(tools, text="Abrir destino", command=self.open_folder).grid(
            row=0, column=4
        )

        table = tk.Frame(card, background=style.CARD)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("fecha", "tamano", "destino", "verificacion")
        self._table = ttk.Treeview(table, columns=columns, show="headings", height=10)
        for column, (title, width, anchor) in zip(
            columns,
            (
                ("Fecha", 170, "w"),
                ("Tamaño", 120, "w"),
                ("Destino", 260, "w"),
                ("Verificación", 150, "w"),
            ),
            strict=True,
        ):
            self._table.heading(column, text=title, anchor=anchor)
            self._table.column(
                column,
                width=round(width * style.scale(self)),
                anchor=anchor,
                stretch=column == "destino",
            )
        style.tag_levels(self._table)
        self._sorter = TableSorter(self._table)
        self._table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, command=self._table.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        style.autoscroll(self._table, scroll)
        self._note = style.label(
            card,
            "",
            color=style.MUTED,
            font=style.SMALL,
            wraplength=round(740 * style.scale(self)),
        )
        self._note.grid(row=4, column=0, sticky="w", pady=(8, 0))

    def refresh(self) -> bool:
        """Lista las copias de cada destino (sin verificarlas)."""
        station = self.app.station
        return self.app.run(
            "Buscando backups...",
            lambda reporter: backup_ops.listing(station, reporter),
            self._show,
            quiet=True,
            on_error=self._unreachable,
        )

    def _unreachable(self, exc: Exception) -> None:
        """Sin destinos accesibles (disco desconectado...): se dice en la tabla."""
        self._table.delete(*self._table.get_children())
        self._paths.clear()
        self._note.configure(
            text=_sentence(str(exc)), foreground=style.LEVEL_COLORS[Level.WARNING]
        )

    def _show(self, reports: list[FolderReport]) -> None:
        """Pinta las copias, de la más reciente a la más antigua."""
        self._table.delete(*self._table.get_children())
        self._sorter.clear()
        self._paths.clear()
        for report in reports:
            folder = report.folder.name or str(report.folder)
            if not report.archives:
                item = self._table.insert(
                    "", "end", values=style.cells("Sin backups", "", folder, "")
                )
                self._sorter.add(item, ("", 0, fold(folder), ""))
            for archive in reversed(report.archives):
                state, level = self._verified.get(archive.path, (PENDING, Level.INFO))
                values = style.cells(
                    archive_label(archive.stamp),
                    parse_size(archive.size),
                    folder,
                    state,
                )
                item = self._table.insert("", "end", values=values, tags=(level.value,))
                self._paths[item] = archive.path
                self._sorter.add(
                    item, (archive.stamp, archive.size, fold(folder), fold(state))
                )
        self._sorter.apply()
        self._note.configure(
            text="Selecciona un backup para restaurarlo. Sin selección se usa el "
            "más reciente. Las claves de API no se guardan: tras restaurar hay que "
            "volver a escribirlas en DeepTutor.",
            foreground=style.MUTED,
        )

    def create(self) -> None:
        """Hace una copia (para y vuelve a arrancar DeepTutor si estaba en marcha)."""
        station, cancel = self.app.station, self.app.worker.cancel

        def run(reporter: Reporter) -> Path:
            created = backup_ops.create(station, reporter, cancel=cancel)
            size = parse_size(created.size)
            reporter.show([ok(f"Backup completado correctamente ({size}).")])
            return created.archive

        def done(archive: Path) -> None:
            self._verified[archive] = ("Verificada", Level.OK)  # se verifica al crear
            self.refresh()

        self.app.run("Haciendo el backup...", run, done, title="Hacer backup")

    def check(self) -> None:
        """Verifica la copia más reciente de cada destino."""
        station = self.app.station

        def run(reporter: Reporter) -> list[FolderReport]:
            reports = backup_ops.check(station, reporter)
            for report in reports:
                reporter.show(report.findings)
            return reports

        def done(reports: list[FolderReport]) -> None:
            for report in reports:
                if report.archives:
                    verified = report.findings[0]
                    ok_level = verified.level is Level.OK
                    self._verified[report.archives[-1].path] = (
                        ("Verificada", Level.OK)
                        if ok_level
                        else ("Dañada", Level.ERROR)
                    )
            self._show(reports)

        self.app.run("Verificando backups...", run, done, title="Comprobar backups")

    def restore(self) -> None:
        """Restaura la copia elegida (o la más reciente), tras confirmarlo."""
        selected = [self._paths[i] for i in self._table.selection() if i in self._paths]
        archive = selected[0] if selected else None
        station = self.app.station
        self.app.run(
            "Preparando la restauración...",
            lambda reporter: backup_ops.plan_restore(station, reporter, archive),
            self._confirm_restore,
            quiet=True,
            on_error=lambda exc: show_message(
                self, "Restaurar", _sentence(str(exc)), Level.WARNING
            ),
        )

    def _confirm_restore(self, plan: RestorePlan, other_root: bool = False) -> None:
        """Pide confirmación y restaura; ofrece aceptar una copia de otra ruta."""
        station = self.app.station
        if not other_root and not ask_yes_no(
            self,
            "Restaurar backup",
            plan.question(station),
            "Restaurar",
            level=Level.WARNING,
        ):
            return

        def run(reporter: Reporter) -> Restored | OtherRootError:
            try:
                restored = backup_ops.restore(
                    station, plan, reporter, other_root=other_root
                )
            except OtherRootError as exc:
                return exc
            reporter.show(_restored_findings(restored))
            return restored

        def done(result: Restored | OtherRootError) -> None:
            if isinstance(result, OtherRootError):
                if ask_yes_no(
                    self,
                    "Restaurar backup",
                    f"{_sentence(str(result))} ¿Restaurarlo de todos modos en esta "
                    "estación?",
                    "Restaurar",
                    level=Level.WARNING,
                ):
                    self._confirm_restore(plan, other_root=True)
                return
            self.refresh()

        self.app.run("Restaurando...", run, done, title="Restaurar backup")

    def open_folder(self) -> None:
        """Abre el primer destino de copias."""
        destinations = self.app.station.backup.destinations
        if destinations and destinations[0].is_dir():
            open_path(destinations[0])
        else:
            show_message(
                self, "Backups", "El destino de los backups no está accesible."
            )


def _sentence(text: str) -> str:
    """Primera letra en mayúscula."""
    return text[:1].upper() + text[1:]


def _restored_findings(result: Restored) -> list:
    """Resultado de una restauración para la actividad."""
    findings = [
        info(f"Lo anterior está en {result.keep}. Bórralo cuando compruebes todo."),
        ok(f"Restaurado: {', '.join(result.replaced)}."),
    ]
    if result.blanked_keys:
        findings.insert(
            0,
            warning(
                f"La copia no lleva las {result.blanked_keys} claves de API: "
                "vuelve a escribirlas en la configuración de DeepTutor."
            ),
        )
    return findings
