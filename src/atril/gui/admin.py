"""Apartado Administración: instalar y actualizar DeepTutor, herramientas y ajustes."""

import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

from atril import install
from atril.checks import Finding, Level, info, ok
from atril.config import load_station
from atril.config.station import STATION_FILE, Station
from atril.gui import style
from atril.gui.desktop import open_path
from atril.ops import Reporter
from atril.ops import installation as installation_ops

if TYPE_CHECKING:
    from atril.gui.app import App

FULL_SHA = re.compile(r"[0-9a-f]{40}")
"""Hash completo de un commit."""


class AdminView(tk.Frame):
    """Instalar y actualizar DeepTutor, parches, diagnóstico, herramientas y ajustes."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las tarjetas de DeepTutor, herramientas y configuración."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._docling = tk.BooleanVar(self, value=True)

        deeptutor = style.card(self, "DeepTutor")
        deeptutor.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        deeptutor.columnconfigure(0, weight=1)
        rows = (
            ("Instalar o completar la instalación", self.install, True),
            ("Actualizar a la última versión", self.update, False),
            ("Volver a una versión anterior…", self.rollback, False),
            ("Aplicar parches", self.patch, False),
            ("Diagnóstico", self.doctor, False),
        )
        for row, (text, command, accent) in enumerate(rows, start=1):
            button = ttk.Button(
                deeptutor,
                text=text,
                command=command,
                style="Accent.TButton" if accent else "TButton",
            )
            app.action(button).grid(row=row, column=0, sticky="ew", pady=3)
        ttk.Checkbutton(
            deeptutor,
            text="Instalar Docling (lee mejor los PDF; descarga grande)",
            variable=self._docling,
        ).grid(row=len(rows) + 1, column=0, sticky="w", pady=(8, 0))

        tools = style.card(self, "Herramientas necesarias")
        tools.grid(row=0, column=1, sticky="nsew", pady=(0, 12))
        tools.columnconfigure(0, weight=1)
        self._tools = tk.Frame(tools, background=style.CARD)
        self._tools.grid(row=1, column=0, sticky="nsew")
        app.action(
            ttk.Button(tools, text="Instalar lo que falta", command=self.install_tools)
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

        config = style.card(self, "Configuración")
        config.grid(row=1, column=0, columnspan=2, sticky="new")
        style.label(
            config,
            f"La configuración de la estación está en {STATION_FILE}. Ábrelo, haz los "
            "cambios, guárdalo y pulsa «Validar». Las claves de API no van ahí: se "
            "escriben en los ajustes de DeepTutor.",
            background=style.CARD,
            color=style.MUTED,
            wraplength=760,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))
        buttons = (
            (f"Abrir {STATION_FILE}", lambda: open_path(app.station.config_file)),
            ("Validar", self.validate),
            ("Abrir carpeta de logs", self.open_logs),
        )
        row = tk.Frame(config, background=style.CARD)
        row.grid(row=2, column=0, columnspan=4, sticky="w")
        for column, (text, command) in enumerate(buttons):
            ttk.Button(row, text=text, command=command).grid(
                row=0, column=column, padx=(0, 6)
            )

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> None:
        """Comprueba qué herramientas hay instaladas."""
        self.app.run(
            "Comprobando herramientas...",
            lambda reporter: install.check_tools(),
            self._show_tools,
            quiet=True,
        )

    def _show_tools(self, findings: list[Finding]) -> None:
        """Pinta cada herramienta con su estado."""
        for widget in self._tools.winfo_children():
            widget.destroy()
        for row, finding in enumerate(findings):
            style.label(
                self._tools,
                style.LEVEL_SYMBOLS[finding.level],
                background=style.CARD,
                font=style.STRONG,
                color=style.LEVEL_COLORS[finding.level],
            ).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=1)
            style.label(
                self._tools, finding.message, background=style.CARD, wraplength=380
            ).grid(row=row, column=1, sticky="nw", pady=1)

    # --- acciones ---------------------------------------------------------------

    def install(self) -> None:
        """Instala DeepTutor o completa la instalación."""
        if not messagebox.askyesno(
            "Instalar DeepTutor",
            "Se descargará DeepTutor y sus dependencias (varios GB con Docling). "
            "Puede tardar bastante. ¿Continuar?",
            parent=self,
        ):
            return
        station, docling = self.app.station, self._docling.get()

        def run(reporter: Reporter) -> None:
            installation_ops.install_deeptutor(station, reporter, docling=docling)
            reporter.show([ok("DeepTutor instalado. Ábrelo desde Inicio.")])

        self.app.run("Instalando DeepTutor...", run, lambda _: self.refresh())

    def update(self, commit: str | None = None) -> None:
        """Actualiza DeepTutor (o lo lleva a ``commit``)."""
        station, docling = self.app.station, self._docling.get()

        def run(reporter: Reporter) -> None:
            result = installation_ops.update_deeptutor(
                station, reporter, docling=docling, commit=commit
            )
            findings = [ok("DeepTutor actualizado.")]
            if result.changed:
                findings.append(
                    info(f"Si da problemas, vuelve a la versión {result.previous}.")
                )
            reporter.show(findings)

        self.app.run("Actualizando DeepTutor...", run, lambda _: None)

    def rollback(self) -> None:
        """Vuelve a un commit concreto (el que indicó la última actualización)."""
        answer = simpledialog.askstring(
            "Volver a una versión anterior",
            "Hash completo del commit (aparece en la actividad tras actualizar):",
            parent=self,
        )
        if answer is None:
            return
        commit = answer.strip().lower()
        if not FULL_SHA.fullmatch(commit):
            messagebox.showerror(
                "Atril", "Hace falta el hash completo (40 caracteres).", parent=self
            )
            return
        self.update(commit)

    def patch(self) -> None:
        """Aplica los parches de ``atril.toml``."""
        station = self.app.station

        def run(reporter: Reporter) -> None:
            findings, changed = installation_ops.patch(station)
            if changed:
                findings.append(
                    info("Reinicia DeepTutor (Parar y Abrir) para que surtan efecto.")
                )
            reporter.show(findings or [info("atril.toml no declara parches.")])

        self.app.run("Aplicando parches...", run, lambda _: None)

    def doctor(self) -> None:
        """Pasa el diagnóstico de DeepTutor."""
        station = self.app.station
        self.app.run(
            "Diagnóstico...",
            lambda reporter: installation_ops.doctor(station, reporter),
            lambda _: None,
        )

    def install_tools(self) -> None:
        """Instala con winget las herramientas que faltan."""
        missing = installation_ops.missing_tools()
        if not missing:
            self.app.log(Level.OK, "No falta ninguna herramienta.")
            return
        if not messagebox.askyesno(
            "Instalar herramientas",
            f"Se instalará con winget: {', '.join(missing)}. Windows puede pedir "
            "permiso de administrador. ¿Continuar?",
            parent=self,
        ):
            return

        def run(reporter: Reporter) -> list[Finding]:
            reporter.show(installation_ops.install_tools(missing, reporter))
            return install.check_tools()

        self.app.run("Instalando herramientas...", run, self._show_tools)

    def validate(self) -> None:
        """Valida ``atril.toml`` y los temarios."""
        root = self.app.station.root

        def run(reporter: Reporter) -> Station:
            station = load_station(root)
            syllabi, warnings = installation_ops.validate(station)
            reporter.show(
                [ok(f"Configuración válida: {len(syllabi)} temarios.")]
                + [Finding(Level.WARNING, message) for message in warnings]
            )
            return station

        def done(station: Station) -> None:
            self.app.station = station  # los cambios valen ya, sin reabrir

        self.app.run("Validando...", run, done)

    def open_logs(self) -> None:
        """Abre la carpeta de logs de atril."""
        folder = self.app.station.logs_dir
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)
