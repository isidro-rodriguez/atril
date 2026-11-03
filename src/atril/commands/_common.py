"""Utilidades compartidas por los comandos: estación, salida y errores."""

from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

import typer

from atril.checks import Finding, Level
from atril.config import ConfigError, Station, find_station, load_station

_STYLE = {
    Level.OK: ("✓", typer.colors.GREEN),
    Level.INFO: ("·", None),
    Level.WARNING: ("!", typer.colors.YELLOW),
    Level.ERROR: ("✗", typer.colors.RED),
}


def fail(message: str) -> NoReturn:
    """Muestra ``message`` como error y termina con código 1."""
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
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


def show(findings: Iterable[Finding]) -> bool:
    """Imprime las comprobaciones; devuelve ``True`` si no hay errores."""
    clean = True
    for finding in findings:
        symbol, color = _STYLE[finding.level]
        typer.secho(f"  {symbol} {finding.message}", fg=color)
        clean = clean and finding.level is not Level.ERROR
    return clean


def title(text: str) -> None:
    """Encabezado de sección."""
    typer.secho(text, bold=True)
