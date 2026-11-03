"""Entrada de la línea de comandos ``atril``."""

from pathlib import Path
from typing import Annotated

import typer

from atril import __version__
from atril.commands import config, deeptutor

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


app.command("validar")(config.validate)
app.command("arrancar")(deeptutor.start)
app.command("parar")(deeptutor.stop)
app.command("estado")(deeptutor.status)
app.command("parches")(deeptutor.patches)


def main() -> None:
    """Ejecuta la aplicación."""
    app()


if __name__ == "__main__":
    main()
