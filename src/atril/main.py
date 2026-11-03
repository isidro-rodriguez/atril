"""Entrada de la línea de comandos ``atril``."""

from pathlib import Path
from typing import Annotated

import typer

from atril import __version__
from atril.config import ConfigError, find_station, load_station, load_syllabi

app = typer.Typer(
    name="atril",
    help="Gestiona una instalación local de DeepTutor y sus temarios.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)


def _show_version(value: bool) -> None:
    """Imprime la versión y termina."""
    if value:
        typer.echo(f"atril {__version__}")
        raise typer.Exit


@app.callback()
def root(
    ctx: typer.Context,
    station: Annotated[
        Path | None,
        typer.Option(
            "--estacion",
            envvar="ATRIL_ESTACION",
            help="Raíz de la estación. Por defecto, la carpeta actual o una "
            "superior que contenga atril.toml.",
            file_okay=False,
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_show_version,
            is_eager=True,
            help="Muestra la versión y termina.",
        ),
    ] = False,
) -> None:
    """Gestiona una instalación local de DeepTutor y sus temarios."""
    ctx.obj = station


def _station_root(ctx: typer.Context) -> Path:
    """Raíz de la estación: ``--estacion`` o búsqueda desde la carpeta actual."""
    explicit: Path | None = ctx.obj
    return explicit if explicit is not None else find_station(Path.cwd())


@app.command("validar")
def validate(ctx: typer.Context) -> None:
    """Valida atril.toml y el temario.toml de cada temario."""
    try:
        station = load_station(_station_root(ctx))
        syllabi, warnings = load_syllabi(station.syllabi_dir)
    except ConfigError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Estación: {station.root}")
    for syllabus in syllabi:
        typer.echo(
            f"  {syllabus.id}: {len(syllabus.knowledge_bases)} KB, "
            f"{len(syllabus.sources)} fuentes"
        )
    for warning in warnings:
        typer.secho(f"Aviso: {warning}", fg=typer.colors.YELLOW)
    typer.secho("Configuración válida.", fg=typer.colors.GREEN)


def main() -> None:
    """Ejecuta la aplicación."""
    app()


if __name__ == "__main__":
    main()
