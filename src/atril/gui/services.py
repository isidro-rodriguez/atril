"""Apartado Servicios: DeepTutor, Ollama y las herramientas que necesita atril."""

import tkinter as tk
import webbrowser
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from atril import ollama
from atril.checks import Level, info, ok
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.gui import style
from atril.gui.model import tool_rows, worst
from atril.ops import Reporter, service
from atril.ops import installation as installation_ops
from atril.ops.installation import Tool

if TYPE_CHECKING:
    from atril.gui.app import App


@dataclass(frozen=True, slots=True)
class ServicesData:
    """Estado de los servicios y herramientas, leído en segundo plano."""

    deeptutor: tuple[Level, str]
    ollama: tuple[Level, str]
    tools: list[Tool]


def load_services(station: Station) -> ServicesData:
    """DeepTutor (instalado, en marcha), Ollama y herramientas."""
    dt = DeepTutor(station)
    if not dt.installed:
        deeptutor = (Level.ERROR, "No instalado")
    elif dt.backend_up() and dt.frontend_up():
        deeptutor = (Level.OK, "En marcha")
    elif dt.backend_up() or dt.frontend_up():
        deeptutor = (Level.WARNING, "Arranque incompleto")
    else:
        deeptutor = (Level.INFO, "Parado")
    if station.ollama is None:
        model = (Level.INFO, "No configurado (opcional: solo para indexar)")
    else:
        status = ollama.get_status(station.ollama.url)
        found = worst(ollama.check(status, station.ollama))
        if not status.running:
            model = (Level.WARNING, "No responde")
        elif found is not None and found.level is not Level.OK:
            model = (found.level, "Necesita atención (ver Diagnóstico)")
        else:
            model = (Level.OK, "Disponible")
    return ServicesData(deeptutor, model, installation_ops.tools())


class ServicesView(tk.Frame):
    """Tarjetas de DeepTutor, Ollama, herramientas e instalación."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las tarjetas."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._docling = tk.BooleanVar(self, value=True)
        self.columnconfigure(0, weight=1, uniform="cols")
        self.columnconfigure(1, weight=1, uniform="cols")
        self.rowconfigure(1, weight=1)

        services = style.card(self, "Servicios")
        services.grid(row=0, column=0, sticky="nsew", padx=(0, 16), pady=(0, 16))
        services.columnconfigure(1, weight=1)
        self._deeptutor = self._service_row(services, 1, "DeepTutor")
        self._ollama = self._service_row(services, 2, "Ollama")
        buttons = tk.Frame(services, background=style.CARD)
        buttons.grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 0))
        for column, (text, command, accent) in enumerate(
            (
                ("Abrir DeepTutor", self.open_deeptutor, True),
                ("Parar DeepTutor", self.stop_deeptutor, False),
                ("Comprobar", self.refresh, False),
            )
        ):
            app.action(
                ttk.Button(
                    buttons,
                    text=text,
                    command=command,
                    style="Accent.TButton" if accent else "TButton",
                )
            ).grid(row=0, column=column, padx=(0, 8))

        tools = style.card(self, "Herramientas")
        tools.grid(row=0, column=1, sticky="nsew", pady=(0, 16))
        tools.columnconfigure(0, weight=1)
        self._tools = tk.Frame(tools, background=style.CARD)
        self._tools.grid(row=1, column=0, sticky="ew")
        self._tools.columnconfigure(1, weight=1)
        app.action(
            ttk.Button(tools, text="Instalar lo que falta", command=self.install_tools)
        ).grid(row=2, column=0, sticky="w", pady=(14, 0))

        setup = style.card(self, "Instalación de DeepTutor")
        setup.grid(row=1, column=0, columnspan=2, sticky="new")
        style.label(
            setup,
            "Instala DeepTutor la primera vez (o completa una instalación a medias) "
            "y actualízalo cuando quieras. Puede tardar bastante y descargar varios "
            "GB.",
            color=style.MUTED,
            wraplength=760,
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        row = tk.Frame(setup, background=style.CARD)
        row.grid(row=2, column=0, sticky="w", pady=(12, 0))
        app.action(
            ttk.Button(
                row,
                text="Instalar o completar",
                style="Accent.TButton",
                command=self.install,
            )
        ).grid(row=0, column=0, padx=(0, 8))
        app.action(
            ttk.Button(row, text="Actualizar", command=self.update_deeptutor)
        ).grid(row=0, column=1, padx=(0, 16))
        ttk.Checkbutton(
            row,
            text="Incluir Docling (lee mejor los PDF; descarga grande)",
            variable=self._docling,
        ).grid(row=0, column=2)

    def _service_row(
        self, parent: tk.Misc, row: int, name: str
    ) -> tuple[tk.Label, tk.Label]:
        """Fila de servicio: icono de nivel, nombre y estado."""
        icon = tk.Label(parent, background=style.CARD)
        icon.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        style.label(parent, name, font=style.STRONG).grid(
            row=row, column=1, sticky="w", pady=4
        )
        state = style.label(parent, "Comprobando…", color=style.MUTED)
        state.grid(row=row, column=2, sticky="e", pady=4)
        return icon, state

    def _set_service(
        self, widgets: tuple[tk.Label, tk.Label], level: Level, text: str
    ) -> None:
        """Pinta el estado de un servicio."""
        icon, state = widgets
        icon.configure(image=style.icon(self, style.LEVEL_ICONS[level], 18))
        state.configure(text=text, foreground=style.LEVEL_COLORS[level])

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Comprueba servicios y herramientas en segundo plano."""
        station = self.app.station
        return self.app.run(
            "Comprobando servicios...",
            lambda reporter: load_services(station),
            self._show,
            quiet=True,
        )

    def _show(self, data: ServicesData) -> None:
        """Pinta servicios y herramientas."""
        self._set_service(self._deeptutor, *data.deeptutor)
        self._set_service(self._ollama, *data.ollama)
        for widget in self._tools.winfo_children():
            widget.destroy()
        for row, (label, state, level) in enumerate(tool_rows(data.tools)):
            tk.Label(
                self._tools,
                image=style.icon(self, style.LEVEL_ICONS[level], 18),
                background=style.CARD,
            ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            style.label(self._tools, label, font=style.STRONG).grid(
                row=row, column=1, sticky="w", pady=3
            )
            style.label(self._tools, state, color=style.LEVEL_COLORS[level]).grid(
                row=row, column=2, sticky="e", pady=3
            )

    # --- acciones ---------------------------------------------------------------

    def open_deeptutor(self) -> None:
        """Arranca DeepTutor si hace falta y lo abre en el navegador."""
        station = self.app.station

        def opened(url: str) -> None:
            webbrowser.open(url)
            self.refresh()

        def run(reporter: Reporter) -> str:
            url = service.open_url(station, reporter)
            reporter.show([ok("DeepTutor en marcha.")])
            return url

        self.app.run(
            "Abriendo DeepTutor (la primera vez tarda unos minutos)...",
            run,
            opened,
            title="Abrir DeepTutor",
        )

    def stop_deeptutor(self) -> None:
        """Detiene DeepTutor y sus procesos de la estación."""
        station = self.app.station

        def stop(reporter: Reporter) -> None:
            service.stop(service.installed(station), reporter)
            reporter.show([ok("DeepTutor detenido.")])

        self.app.run(
            "Deteniendo DeepTutor...",
            stop,
            lambda _: self.refresh(),
            title="Parar DeepTutor",
        )

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

        self.app.run(
            "Instalando DeepTutor...",
            run,
            lambda _: self.refresh(),
            title="Instalar DeepTutor",
        )

    def update_deeptutor(self, commit: str | None = None) -> None:
        """Actualiza DeepTutor (o lo lleva a ``commit``)."""
        station, docling = self.app.station, self._docling.get()

        def run(reporter: Reporter) -> None:
            result = installation_ops.update_deeptutor(
                station, reporter, docling=docling, commit=commit
            )
            if result.changed:
                reporter.show(
                    [
                        info(
                            "Si la nueva versión da problemas, vuelve a la anterior "
                            f"en Diagnóstico (commit {result.previous})."
                        ),
                        ok("DeepTutor actualizado."),
                    ]
                )
            else:
                reporter.show([ok("Ya está en la última versión.")])

        self.app.run(
            "Actualizando DeepTutor...",
            run,
            lambda _: self.refresh(),
            title="Actualizar DeepTutor",
        )

    def install_tools(self) -> None:
        """Instala con winget las herramientas que faltan."""
        missing = installation_ops.missing_tools()
        if not missing:
            messagebox.showinfo("Atril", "No falta ninguna herramienta.", parent=self)
            return
        if not messagebox.askyesno(
            "Instalar herramientas",
            f"Se instalará con winget: {', '.join(missing)}. Windows puede pedir "
            "permiso de administrador. ¿Continuar?",
            parent=self,
        ):
            return

        def run(reporter: Reporter) -> None:
            reporter.show(installation_ops.install_tools(missing, reporter))

        self.app.run(
            "Instalando herramientas...",
            run,
            lambda _: self.refresh(),
            title="Instalar herramientas",
        )
