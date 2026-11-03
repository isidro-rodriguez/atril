"""Comandos de configuración: ``atril validar``."""

import typer

from atril.commands._common import fail, get_station
from atril.config import ConfigError, load_syllabi


def validate(ctx: typer.Context) -> None:
    """Valida atril.toml y el temario.toml de cada temario."""
    station = get_station(ctx)
    try:
        syllabi, warnings = load_syllabi(station.syllabi_dir)
    except ConfigError as exc:
        fail(str(exc))

    typer.echo(f"Estación: {station.root}")
    for syllabus in syllabi:
        typer.echo(
            f"  {syllabus.id}: {len(syllabus.knowledge_bases)} KB, "
            f"{len(syllabus.sources)} fuentes"
        )
    for warning in warnings:
        typer.secho(f"Aviso: {warning}", fg=typer.colors.YELLOW)
    typer.secho("Configuración válida.", fg=typer.colors.GREEN)
