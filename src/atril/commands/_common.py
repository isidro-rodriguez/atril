"""Utilidades compartidas por los comandos: estación, consola Rich y errores.

Toda la salida pasa por :data:`console` (y :data:`err_console` para errores). El
texto que viene de fuera (rutas, mensajes de configuración con ``[[fuente]]``,
líneas de comandos) se escapa para que Rich no lo interprete como markup.
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NoReturn

import typer
from acodo.utils import valid_slug
from rich.console import Console
from rich.markup import escape

from atril.checks import Finding, Level
from atril.config import (
    ConfigError,
    Station,
    Syllabus,
    find_station,
    load_station,
    load_syllabi,
    load_syllabus,
)
from atril.config.syllabus import KnowledgeBase

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


def get_syllabus(ctx: typer.Context, syllabus_id: str) -> Syllabus:
    """Carga un temario por id; termina con error si no existe o no es válido."""
    station = get_station(ctx)
    if not valid_slug(syllabus_id):
        fail(
            f"id de temario no válido: {syllabus_id!r} (minúsculas, cifras y guiones)."
        )
    root = station.syllabi_dir / syllabus_id
    if not (root / "temario.toml").is_file():
        found = sorted(
            p.parent.name for p in station.syllabi_dir.glob("*/temario.toml")
        )
        names = ", ".join(found) or "ninguno"
        fail(f"no existe el temario {syllabus_id!r} (disponibles: {names}).")
    try:
        return load_syllabus(root)
    except ConfigError as exc:
        fail(str(exc))


def find_kb(ctx: typer.Context, kb_id: str) -> tuple[Syllabus, KnowledgeBase]:
    """Temario y KB a partir del id de KB (único en la estación)."""
    station = get_station(ctx)
    try:
        syllabi, _ = load_syllabi(station.syllabi_dir)
    except ConfigError as exc:
        fail(str(exc))
    for syllabus in syllabi:
        for kb in syllabus.knowledge_bases:
            if kb.id == kb_id:
                return syllabus, kb
    known = ", ".join(kb.id for s in syllabi for kb in s.knowledge_bases) or "ninguna"
    fail(f"no existe la KB {kb_id!r} en ningún temario (disponibles: {known}).")


def load_or_fail[T](factory: Callable[[], T]) -> T:
    """Ejecuta ``factory``; un fichero de estado o de configuración dañado termina."""
    try:
        return factory()
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
