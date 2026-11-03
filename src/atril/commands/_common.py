"""Utilidades compartidas por los comandos: estación, consola Rich y errores.

Toda la salida pasa por :data:`console` (y :data:`err_console` para errores). El
texto que viene de fuera (rutas, mensajes de configuración con ``[[fuente]]``,
líneas de comandos) se escapa para que Rich no lo interprete como markup.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.markup import escape

from atril.checks import Finding, Level
from atril.config import ConfigError, Station, find_station, load_station

console = Console(soft_wrap=True)
"""Consola de salida normal; ``soft_wrap`` evita cortar rutas y mensajes largos."""

err_console = Console(stderr=True, soft_wrap=True)
"""Consola de errores."""

_STYLE = {
    Level.OK: ("✓", "green"),
    Level.INFO: ("·", "dim"),
    Level.WARNING: ("!", "yellow"),
    Level.ERROR: ("✗", "bold red"),
}


def fail(message: str) -> NoReturn:
    """Muestra ``message`` como error y termina con código 1."""
    err_console.print(f"[bold red]Error:[/] {escape(message)}")
    raise typer.Exit(1)


def station_root(ctx: typer.Context) -> Path:
    """Raíz de la estación: ``--estacion`` o búsqueda desde la carpeta actual."""
    explicit: Path | None = ctx.obj
    return explicit if explicit is not None else find_station(Path.cwd())


def get_station(ctx: typer.Context) -> Station:
    """Carga ``atril.toml``; termina con error si falta o no es válido."""
    try:
        return load_station(station_root(ctx))
    except ConfigError as exc:
        fail(str(exc))


def show(findings: Iterable[Finding], title: str | None = None) -> bool:
    """Muestra las comprobaciones, una por línea, con símbolo y color por nivel.

    Args:
        findings: Comprobaciones, en el orden en que se muestran.
        title: Título de la sección, si lo hay.

    Returns:
        ``True`` si ninguna es un error.
    """
    if title:
        console.rule(f"[bold]{escape(title)}[/]", align="left")
    clean = True
    for finding in findings:
        symbol, style = _STYLE[finding.level]
        console.print(f"  [{style}]{symbol}[/] {escape(finding.message)}")
        clean = clean and finding.level is not Level.ERROR
    return clean


def success(message: str) -> None:
    """Mensaje final de éxito."""
    console.print(f"[bold green]{escape(message)}[/]")
