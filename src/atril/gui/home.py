"""Apartado Inicio: estado general con Arrancar/Parar y las herramientas.

Arrancar abre Ollama (si hace falta para indexar) y DeepTutor, y lo abre en el
navegador; Parar solo detiene DeepTutor. Cada herramienta tiene una sola acción
(instalar, arrancar o parar). Ollama solo se para si lo abrió atril.
"""

import shutil
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from atril import ollama
from atril.checks import Level, ok
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.gui import style
from atril.gui.dialogs import ask_yes_no
from atril.gui.model import Action, Facts, ToolCard, overall, tool_cards
from atril.gui.widgets import ToolTile
from atril.install import run_command, tool
from atril.ops import Reporter, service
from atril.ops import installation as installation_ops

if TYPE_CHECKING:
    from atril.gui.app import App

CLAUDE_CODE_URL = "https://docs.claude.com/en/docs/claude-code/setup"
"""Instrucciones oficiales para instalar Claude Code."""

WINGET_TOOLS = {"git": "git", "uv": "uv", "node": "node", "ollama": "ollama"}
"""Herramientas de Inicio que se instalan con ``winget``."""


def load_facts(station: Station) -> Facts:
    """Estado de DeepTutor, Ollama y herramientas (sondeos rápidos, sin escaneos)."""
    dt = DeepTutor(station)
    installed = dt.installed
    status = ollama.get_status(service.ollama_url(station))
    return Facts(
        deeptutor_installed=installed,
        backend_up=installed and dt.backend_up(),
        frontend_up=installed and dt.frontend_up(),
        ollama_installed=ollama.is_installed(),
        ollama_running=status.running,
        ollama_ours=status.running and service.ollama_owner(station) is not None,
        ollama_models=tuple(status.installed),
        tools={
            name: shutil.which(name) is not None
            for name in ("git", "uv", "node", "claude")
        },
        llm=station.deeptutor.llm,
        ollama_required=station.ollama is not None,
        pending=service.patch_findings(station) if installed else [],
    )


class HomeView(tk.Frame):
    """Estado general con el botón Arrancar/Parar y las seis herramientas."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye las dos tarjetas."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._facts: Facts | None = None
        self.columnconfigure(0, weight=1)
        self._build_status().grid(row=0, column=0, sticky="ew")
        self._build_tools().grid(row=1, column=0, sticky="ew", pady=(14, 0))

    def _build_status(self) -> ttk.Frame:
        """Tarjeta de estado: icono, titular, frase y el botón ancho."""
        card = style.card(self, "Estado general")
        card.columnconfigure(1, weight=1)
        self._icon = tk.Label(card, background=style.CARD)
        self._icon.grid(row=1, column=0, rowspan=2, sticky="nw", padx=(0, 14))
        self._headline = style.label(card, "Comprobando…", font=style.TITLE)
        self._headline.grid(row=1, column=1, sticky="sw")
        self._sentence = style.label(card, "", color=style.MUTED, wraplength=640)
        self._sentence.grid(row=2, column=1, sticky="nw")
        buttons = tk.Frame(card, background=style.CARD)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        buttons.columnconfigure(0, weight=1)
        self._toggle = self.app.action(
            ttk.Button(
                buttons, text="Arrancar", style="Accent.TButton", command=self.toggle
            )
        )
        self._toggle.grid(row=0, column=0, sticky="ew", ipady=6)
        self._open = ttk.Button(
            buttons, text="Abrir en el navegador", command=self.open_browser
        )
        self._open.grid(row=0, column=1, sticky="e", padx=(10, 0), ipady=6)
        self._open.grid_remove()
        return card

    def _build_tools(self) -> ttk.Frame:
        """Tarjeta de herramientas: baldosas en tres columnas."""
        card = style.card(self, "Herramientas")
        grid = tk.Frame(card, background=style.CARD)
        grid.grid(row=1, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        self._tiles: list[ToolTile] = []
        for index in range(6):
            grid.columnconfigure(index % 3, weight=1, uniform="tools")
            tile = ToolTile(grid, self.act)
            tile.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=(0 if index % 3 == 0 else 10, 0),
                pady=(0 if index < 3 else 10, 0),
            )
            self.app.action(tile.button)
            self._tiles.append(tile)
        return card

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Comprueba servicios y herramientas en segundo plano."""
        station = self.app.station
        return self.app.run(
            "Comprobando...",
            lambda reporter: load_facts(station),
            self._show,
            quiet=True,
        )

    def _show(self, facts: Facts) -> None:
        """Pinta el estado general, el botón y las herramientas."""
        self._facts = facts
        self.app.set_facts(facts)
        level, headline, sentence = overall(facts)
        self._icon.configure(image=style.icon(self, style.LEVEL_ICONS[level], 36))
        self._headline.configure(text=headline)
        self._sentence.configure(text=sentence)
        running = facts.backend_up or facts.frontend_up
        text = "Parar" if running else "Arrancar"
        if not facts.deeptutor_installed:
            text = "Instalar DeepTutor"
        self._toggle.configure(
            text=text, style="TButton" if running else "Accent.TButton"
        )
        if facts.deeptutor_running:
            self._open.grid()
        else:
            self._open.grid_remove()
        for tile, card in zip(self._tiles, tool_cards(facts), strict=True):
            tile.show(card)

    # --- acciones ---------------------------------------------------------------

    def toggle(self) -> None:
        """Arranca (y abre) o para atril según su estado."""
        facts = self._facts
        if facts is not None and not facts.deeptutor_installed:
            self.install_deeptutor()
        elif facts is not None and (facts.backend_up or facts.frontend_up):
            self.stop_deeptutor()
        else:
            self.start()

    def start(self) -> None:
        """Abre Ollama si hace falta, arranca DeepTutor y lo abre en el navegador."""
        station = self.app.station

        def run(reporter: Reporter) -> str:
            url = service.open_url(station, reporter)
            reporter.show([ok("DeepTutor en marcha.")])
            return url

        def opened(url: str) -> None:
            webbrowser.open(url)
            self.refresh()

        self.app.run(
            "Arrancando (la primera vez tarda unos minutos)...",
            run,
            opened,
            title="Arrancar",
        )

    def open_browser(self) -> None:
        """Abre DeepTutor en el navegador."""
        webbrowser.open(DeepTutor(self.app.station).frontend_url)

    def stop_deeptutor(self) -> None:
        """Detiene DeepTutor y sus procesos de la estación."""
        station = self.app.station

        def stop(reporter: Reporter) -> None:
            service.stop(service.installed(station), reporter)
            reporter.show([ok("DeepTutor detenido.")])

        self.app.run(
            "Parando DeepTutor...", stop, lambda _: self.refresh(), title="Parar"
        )

    def install_deeptutor(self) -> None:
        """Instala DeepTutor (con Docling si el parser lo usa)."""
        if not ask_yes_no(
            self,
            "Instalar DeepTutor",
            "Se descargará DeepTutor y sus dependencias (varios GB). Puede tardar "
            "bastante.",
            "Instalar",
        ):
            return
        station = self.app.station

        def run(reporter: Reporter) -> None:
            installation_ops.install_deeptutor(station, reporter)
            reporter.show([ok("DeepTutor instalado.")])

        self.app.run(
            "Instalando DeepTutor...",
            run,
            lambda _: self.refresh(),
            title="Instalar DeepTutor",
        )

    def act(self, card: ToolCard) -> None:
        """Acción de una baldosa."""
        match card.key, card.action:
            case "deeptutor", Action.INSTALL:
                self.install_deeptutor()
            case "deeptutor", Action.START:
                self.start()
            case "deeptutor", Action.STOP:
                self.stop_deeptutor()
            case "ollama", Action.START:
                self._ollama(
                    service.start_ollama, "Arrancando Ollama...", "Arrancar Ollama"
                )
            case "ollama", Action.STOP:
                self._ollama(service.stop_ollama, "Parando Ollama...", "Parar Ollama")
            case "asistente", Action.INSTALL:
                webbrowser.open(CLAUDE_CODE_URL)
            case "asistente", Action.PULL:
                self._pull(card.name)
            case key, Action.INSTALL if key in WINGET_TOOLS:
                self._winget(WINGET_TOOLS[key], card.name)

    def _ollama(
        self, action: Callable[[Station, Reporter], None], text: str, title: str
    ) -> None:
        """Arranca o para Ollama."""
        station = self.app.station
        self.app.run(
            text,
            lambda reporter: action(station, reporter),
            lambda _: self.refresh(),
            title=title,
        )

    def _pull(self, model: str) -> None:
        """Descarga un modelo de chat de Ollama."""

        def run(reporter: Reporter) -> None:
            with reporter.busy(f"Descargando {model} (puede tardar)..."):
                code = run_command([tool("ollama"), "pull", model])
            if code != 0:
                raise AtrilError(f"Ollama no ha podido descargar {model}.")
            reporter.show([ok(f"{model} descargado.")])

        self.app.run(
            "Descargando el modelo...",
            run,
            lambda _: self.refresh(),
            title="Descargar modelo",
        )

    def _winget(self, name: str, label: str) -> None:
        """Instala una herramienta con winget."""
        if not ask_yes_no(
            self,
            f"Instalar {label}",
            f"Se instalará {label} con winget. Windows puede pedir permiso de "
            "administrador.",
            "Instalar",
        ):
            return

        def run(reporter: Reporter) -> None:
            findings = installation_ops.install_tools([name], reporter)
            reporter.show(findings)
            if any(f.level is Level.ERROR for f in findings):
                raise AtrilError(f"no se ha podido instalar {label}.")

        self.app.run(
            f"Instalando {label}...",
            run,
            lambda _: self.refresh(),
            title=f"Instalar {label}",
        )
