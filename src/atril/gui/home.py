"""Apartado Inicio: estado general con Arrancar/Parar y las herramientas.

Arrancar abre Ollama (si hace falta para indexar) y DeepTutor, y lo abre en el
navegador; Parar solo detiene DeepTutor. Cada herramienta tiene una sola acción
(instalar, arrancar o parar). Ollama solo se para si lo abrió atril.
"""

import shutil
import subprocess
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import TYPE_CHECKING

from atril import backup, ollama
from atril.checks import Level, ok
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
    HomeStat,
    ToolCard,
    backup_stat,
    load_all,
    overall,
    sources_stat,
    syllabi_stat,
    tool_cards,
)
from atril.gui.widgets import ToolTile
from atril.install import run_command, tool
from atril.ops import Reporter, service
from atril.ops import backup as backup_ops
from atril.ops import installation as installation_ops
from atril.processes import no_window

if TYPE_CHECKING:
    from atril.gui.app import App

SENTENCE_WIDTH = 410
"""Ancho máximo (a 100 %) de la frase del estado general: una sola línea."""

STAT_WIDTH = 190
"""Ancho máximo (a 100 %) del texto de cada dato del estado general."""

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
    stats: tuple[HomeStat, ...]


STAT_ICONS = ("book-copy-dato", "file-stack-dato", "archive-dato")
"""Iconos de los datos del estado general: temarios, fuentes y último backup."""


def load_home(station: Station, active: str | None = None) -> HomeData:
    """Estado de servicios y herramientas, y los datos de temarios y copias."""
    syllabi = load_all(station)
    return HomeData(
        load_facts(station),
        (syllabi_stat(syllabi, active), sources_stat(syllabi), _backup_stat(station)),
    )


def _backup_stat(station: Station) -> HomeStat:
    """Copia más reciente de los destinos accesibles y su última comprobación."""
    found = [
        archive
        for folder in station.backup.destinations
        if backup.is_reachable(folder)
        for archive in backup.archives(folder)
    ]
    if not found:
        return backup_stat(None, None)
    latest = max(found, key=lambda archive: archive.stamp)
    verification = backup_ops.verifications(station).get(latest.path)
    return backup_stat(latest.stamp, verification.ok if verification else None)


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
        self._shown_stats: tuple[HomeStat, ...] = ()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_status().grid(row=0, column=0, sticky="nsew")
        self._build_tools().grid(row=1, column=0, sticky="ew", pady=(14, 0))

    def _build_status(self) -> ttk.Frame:
        """Estado general: icono, estado y botones arriba, y tres datos abajo.

        Es el bloque principal de la ventana: ocupa el alto que dejan las
        herramientas, con el estado centrado en el hueco sobre los datos.
        """
        factor = style.scale(self)
        card = style.card(self, "Estado general")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        card.rowconfigure(3, weight=1)
        top = tk.Frame(card, background=style.CARD)
        top.grid(row=2, column=0, sticky="ew")
        top.columnconfigure(2, weight=1)
        self._icon = tk.Label(top, background=style.CARD)
        self._icon.grid(row=0, column=0, rowspan=2, padx=(4, 0))
        tk.Frame(top, background=style.BORDER, width=max(1, round(factor))).grid(
            row=0, column=1, rowspan=2, sticky="ns", padx=round(20 * factor)
        )
        self._headline = style.label(top, "Comprobando…", font=style.HEADLINE)
        self._headline.grid(row=0, column=2, sticky="sw")
        self._sentence = style.label(top, "", font=style.LEAD, color=style.MUTED)
        self._sentence.grid(row=1, column=2, sticky="nw", pady=(4, 0))
        buttons = tk.Frame(top, background=style.CARD)
        buttons.grid(row=0, column=3, rowspan=2, sticky="e", padx=(16, 0))
        buttons.columnconfigure(0, weight=1)
        self._open = ttk.Button(
            buttons,
            text="Abrir en el navegador",
            compound="left",
            command=self.open_browser,
        )
        self._open.grid(row=0, column=0, sticky="ew", ipady=18, pady=(0, 10))
        self._open.grid_remove()
        self._toggle = self.app.action(
            ttk.Button(
                buttons,
                text="Arrancar DeepTutor",
                compound="left",
                style="Accent.TButton",
                command=self.toggle,
            )
        )
        self._toggle.grid(row=1, column=0, sticky="ew", ipady=18)
        tk.Frame(card, background=style.BORDER, height=max(1, round(factor))).grid(
            row=4, column=0, sticky="ew", pady=(round(10 * factor), round(16 * factor))
        )
        stats = tk.Frame(card, background=style.CARD)
        stats.grid(row=5, column=0, sticky="ew")
        self._stats: list[tuple[tk.Label, tk.Canvas, tk.Label]] = []
        for index, name in enumerate(STAT_ICONS):
            if index:
                tk.Frame(
                    stats, background=style.BORDER, width=max(1, round(factor))
                ).grid(row=0, column=2 * index - 1, sticky="ns", pady=2)
            stats.columnconfigure(2 * index, weight=1, uniform="stats")
            self._stats.append(self._stat(stats, 2 * index, name))
        return card

    def _stat(
        self, parent: tk.Frame, column: int, name: str
    ) -> tuple[tk.Label, tk.Canvas, tk.Label]:
        """Un dato del pie: icono, título y estado con su punto de color."""
        factor = style.scale(self)
        box = tk.Frame(parent, background=style.CARD, cursor="hand2")
        box.grid(
            row=0,
            column=column,
            sticky="w",
            padx=(0 if column == 0 else round(20 * factor), 0),
        )
        image = tk.Label(
            box, image=style.icon(self, name, 40), background=style.CARD, cursor="hand2"
        )
        image.grid(row=0, column=0, rowspan=2, padx=(0, round(14 * factor)))
        title = style.label(box, "", font=style.STRONG)
        title.grid(row=0, column=1, columnspan=2, sticky="sw")
        size = round(9 * factor)
        dot = tk.Canvas(
            box, width=size, height=size, background=style.CARD, highlightthickness=0
        )
        dot.create_oval(0, 0, size - 1, size - 1, fill=style.MUTED, outline="")
        dot.grid(row=1, column=1, sticky="w", padx=(0, round(6 * factor)))
        text = style.label(box, "", font=style.SMALL, color=style.MUTED)
        text.grid(row=1, column=2, sticky="nw")
        index = column // 2
        for widget in (box, image, title, dot, text):
            widget.bind("<Button-1>", lambda _event: self._go(index))
        return title, dot, text

    def _go(self, index: int) -> None:
        """Lleva al apartado del dato pulsado."""
        if self._shown_stats:
            self.app.show_view(self._shown_stats[index].view)

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
        active = self.app.syllabus_id
        started = self.app.run(
            "Comprobando...",
            lambda reporter: load_home(station, active),
            self._show,
            quiet=True,
        )
        return started

    def _show(self, data: HomeData) -> None:
        """Pinta el estado general, el botón y las herramientas."""
        facts = data.facts
        self._facts = facts
        self.app.set_facts(facts)
        level, headline, sentence = overall(facts)
        self._icon.configure(image=style.icon(self, style.LEVEL_ICONS[level], 104))
        self._headline.configure(text=headline)
        self._sentence.configure(text=_one_line(self._sentence, sentence))
        running = facts.backend_up or facts.frontend_up
        text, symbol = (
            ("Parar DeepTutor", "square") if running else ("Arrancar DeepTutor", "play")
        )
        if not facts.deeptutor_installed:
            text, symbol = "Instalar DeepTutor", "download"
        variant = "boton" if running else "boton-acento"
        self._toggle.configure(
            text=text,
            image=style.icon(self, f"{symbol}-{variant}", 18),
            style="TButton" if running else "Accent.TButton",
        )
        if facts.deeptutor_running:
            # En marcha, lo principal es abrirlo: el botón destacado es ese.
            self._open.configure(
                style="Accent.TButton",
                image=style.icon(self, "globe-boton-acento", 18),
            )
            self._open.grid()
        else:
            self._open.grid_remove()
        self._shown_stats = data.stats
        for (title, dot, label), stat in zip(self._stats, data.stats, strict=True):
            title.configure(text=stat.title)
            dot.itemconfigure(1, fill=style.LEVEL_COLORS[stat.level])
            label.configure(text=_one_line(label, stat.text, STAT_WIDTH))
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


def _one_line(label: tk.Label, text: str, width: int = SENTENCE_WIDTH) -> str:
    """``text`` abreviado con «…» para que quepa en una línea de ``label``.

    El ancho disponible es el de la columna del texto en Inicio.
    """
    width = round(width * style.scale(label))
    font = tkfont.nametofont(str(label.cget("font")), root=label)
    if font.measure(text) <= width:
        return text
    while text and font.measure(f"{text}…") > width:
        text = text[:-1]
    return f"{text.rstrip(' ,.:')}…"
