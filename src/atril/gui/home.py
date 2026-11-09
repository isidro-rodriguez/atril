"""Apartado Inicio: estado general con Arrancar/Parar y las herramientas.

Arrancar abre Ollama (si hace falta para indexar) y DeepTutor, y lo abre en el
navegador; Parar solo detiene DeepTutor. Cada herramienta tiene una sola acción
(instalar, arrancar o parar). Ollama solo se para si lo abrió atril.
"""

import contextlib
import shutil
import subprocess
import tkinter as tk
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import TYPE_CHECKING

from atril import backup, ollama
from atril.checks import Level, ok
from atril.config import ConfigError, load_syllabi
from atril.config.station import Station
from atril.deeptutor import Assistant, DeepTutor, active_assistant
from atril.errors import AtrilError
from atril.gui import style
from atril.gui.dialogs import ask_yes_no
from atril.gui.model import (
    ORDER,
    WEBSITES,
    Action,
    Facts,
    Summary,
    ToolCard,
    archive_label,
    overall,
    summary_line,
    tool_cards,
)
from atril.gui.widgets import ToolTile
from atril.install import run_command, tool
from atril.knowledge import Ledger, ledger_path
from atril.ops import Reporter, service
from atril.ops import installation as installation_ops
from atril.processes import no_window

if TYPE_CHECKING:
    from atril.gui.app import App

CLAUDE_CODE_URL = "https://docs.claude.com/en/docs/claude-code/setup"
"""Instrucciones oficiales para instalar Claude Code."""

WINGET_TOOLS = {
    "git": "git",
    "uv": "uv",
    "node": "node",
    "npm": "npm",
    "ollama": "ollama",
}
"""Herramientas de Inicio que se instalan con ``winget``."""


@dataclass(frozen=True, slots=True)
class HomeData:
    """Lo que necesita Inicio, leído en segundo plano."""

    facts: Facts
    summary: Summary


def load_home(station: Station) -> HomeData:
    """Estado de servicios y herramientas y el resumen de la estación."""
    stamps = [
        archive.stamp
        for folder in station.backup.destinations
        if backup.is_reachable(folder)
        for archive in backup.archives(folder)
    ]
    syllabi_count = sources = indexed = 0
    with contextlib.suppress(ConfigError, OSError):
        syllabi, _ = load_syllabi(station.syllabi_dir)
        for syllabus in syllabi:
            syllabi_count += 1
            sources += len(syllabus.sources)
            with contextlib.suppress(AtrilError, OSError):
                ledger = Ledger(ledger_path(syllabus))
                current = {source.id for source in syllabus.sources}
                indexed += len(
                    {key for kb in ledger.kbs.values() for key in kb.sources} & current
                )
    summary = Summary(
        syllabi_count,
        sources,
        indexed,
        archive_label(max(stamps)) if stamps else None,
    )
    return HomeData(load_facts(station), summary)


def load_facts(station: Station) -> Facts:
    """Estado de DeepTutor, Ollama y herramientas (sondeos rápidos, sin escaneos)."""
    dt = DeepTutor(station)
    installed = dt.installed
    status = ollama.get_status(service.ollama_url(station))
    tools = {
        name: shutil.which(name) is not None
        for name in ("git", "uv", "node", "npm", "claude")
    }
    tools["python"] = _python_ready(station, uv=tools["uv"])
    return Facts(
        deeptutor_installed=installed,
        backend_up=installed and dt.backend_up(),
        frontend_up=installed and dt.frontend_up(),
        ollama_installed=ollama.is_installed(),
        ollama_running=status.running,
        ollama_ours=status.running and service.ollama_owner(station) is not None,
        ollama_models=tuple(status.installed),
        tools=tools,
        assistant=_assistant(station),
        ollama_required=station.ollama is not None,
        pending=service.patch_findings(station) if installed else [],
    )


def _python_ready(station: Station, *, uv: bool) -> bool:
    """El Python de ``atril.toml`` está: en el entorno de DeepTutor o en uv."""
    if station.venv_python.is_file():
        return True
    if not uv:
        return False
    result = subprocess.run(
        [tool("uv"), "python", "find", station.deeptutor.python],
        capture_output=True,
        check=False,
        creationflags=no_window(),
    )
    return result.returncode == 0


def _assistant(station: Station) -> Assistant | None:
    """Asistente activo en DeepTutor o, si aún no hay catálogo, el de atril.toml."""
    found = active_assistant(station)
    if found is not None:
        return found
    llm = station.deeptutor.llm
    return Assistant(llm.provider, llm.model, False) if llm else None


class HomeView(tk.Frame):
    """Estado general con el botón Arrancar/Parar y las herramientas."""

    def __init__(self, parent: tk.Misc, app: "App") -> None:
        """Construye el bloque de estado (principal) y las herramientas (compactas)."""
        super().__init__(parent, background=style.PAGE)
        self.app = app
        self._facts: Facts | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_status().grid(row=0, column=0, sticky="nsew")
        self._build_tools().grid(row=1, column=0, sticky="ew", pady=(14, 0))

    def _build_status(self) -> ttk.Frame:
        """Estado general: icono y titular grandes, frase, resumen y el botón.

        Es el bloque principal de la ventana: ocupa el alto que dejan las
        herramientas, con el botón abajo a la derecha.
        """
        card = style.card(self, "Estado general")
        card.columnconfigure(1, weight=1)
        card.rowconfigure(1, weight=1)
        card.rowconfigure(5, weight=1)
        self._icon = tk.Label(card, background=style.CARD)
        self._icon.grid(row=2, column=0, rowspan=2, sticky="w", padx=(0, 22))
        self._headline = style.label(card, "Comprobando…", font=style.HEADLINE)
        self._headline.grid(row=2, column=1, sticky="sw")
        self._sentence = style.label(
            card,
            "",
            font=style.LEAD,
            color=style.MUTED,
            wraplength=round(660 * style.scale(self)),
        )
        self._sentence.grid(row=3, column=1, sticky="nw", pady=(2, 0))
        # Resumen en la línea del título, a la derecha: no quita alto al estado.
        self._summary = style.label(card, "", color=style.MUTED)
        self._summary.grid(row=0, column=1, sticky="e", pady=(0, 10))
        buttons = tk.Frame(card, background=style.CARD)
        buttons.grid(row=6, column=0, columnspan=2, sticky="se")
        self._open = ttk.Button(
            buttons, text="Abrir en el navegador", command=self.open_browser
        )
        self._open.grid(row=0, column=0, sticky="e", padx=(0, 10), ipady=30)
        self._open.grid_remove()
        self._toggle = self.app.action(
            ttk.Button(
                buttons,
                text="Arrancar",
                style="Accent.TButton",
                command=self.toggle,
                width=18,
            )
        )
        self._toggle.grid(row=0, column=1, sticky="e", ipady=30)
        return card

    def _build_tools(self) -> ttk.Frame:
        """Herramientas en baldosas de una fila: dos por fila, todas iguales."""
        card = style.card(self, "Herramientas")
        card.columnconfigure(0, weight=1)
        grid = tk.Frame(card, background=style.CARD)
        grid.grid(row=1, column=0, sticky="ew")
        self._tiles: list[ToolTile] = []
        for index in range(len(ORDER)):
            row, column = divmod(index, 2)
            grid.columnconfigure(column, weight=1, uniform="tools")
            tile = ToolTile(grid, self.act, self.open_website)
            tile.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 10, 0),
                pady=(0 if row == 0 else 8, 0),
            )
            self.app.action(tile.button)
            self._tiles.append(tile)
        return card

    # --- datos ------------------------------------------------------------------

    def refresh(self) -> bool:
        """Comprueba servicios y herramientas en segundo plano."""
        station = self.app.station
        started = self.app.run(
            "Comprobando...",
            lambda reporter: load_home(station),
            self._show,
            quiet=True,
        )
        return started

    def _show(self, data: HomeData) -> None:
        """Pinta el estado general, el botón y las herramientas."""
        facts = data.facts
        self._facts = facts
        self._summary.configure(text=summary_line(data.summary))
        self.app.set_facts(facts)
        level, headline, sentence = overall(facts)
        self._icon.configure(image=style.icon(self, style.LEVEL_ICONS[level], 88))
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
            # En marcha, lo principal es abrirlo: el botón destacado es ese.
            self._open.configure(style="Accent.TButton")
            self._open.grid()
        else:
            self._open.grid_remove()
        for tile, card in zip(self._tiles, tool_cards(facts), strict=True):
            tile.show(card, website=card.key in WEBSITES)

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

    def open_website(self, card: ToolCard) -> None:
        """Abre la web de la herramienta (el asistente no tiene)."""
        if url := WEBSITES.get(card.key):
            webbrowser.open(url)

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
            case "asistente", Action.PULL if self._facts and self._facts.assistant:
                self._pull(self._facts.assistant.model.removeprefix("ollama/"))
            case "python", Action.INSTALL:
                self._python()
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

    def _python(self) -> None:
        """Instala con uv el Python que pide ``atril.toml``."""
        version = self.app.station.deeptutor.python

        def run(reporter: Reporter) -> None:
            if shutil.which("uv") is None:
                raise AtrilError("instala antes uv: con él se instala Python.")
            with reporter.busy(f"Instalando Python {version}..."):
                code = run_command([tool("uv"), "python", "install", version])
            if code != 0:
                raise AtrilError(f"uv no ha podido instalar Python {version}.")
            reporter.show([ok(f"Python {version} instalado.")])

        self.app.run(
            "Instalando Python...",
            run,
            lambda _: self.refresh(),
            title="Instalar Python",
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
