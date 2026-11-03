"""Entrada de la línea de comandos ``atril``."""

from pathlib import Path
from typing import Annotated

import typer

from atril import __version__
from atril.commands import config, deeptutor
from atril.commands._common import console

app = typer.Typer(
    name="atril",
    help="Gestiona una instalación local de DeepTutor y sus temarios.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


def _show_version(value: bool) -> None:
    """Imprime la versión y termina."""
    if value:
        console.print(f"atril [bold]{__version__}[/]")
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
            "superior que contenga [bold]atril.toml[/].",
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


_CONFIG = "Configuración"
_DEEPTUTOR = "DeepTutor"

app.command("validar", rich_help_panel=_CONFIG)(config.validate)
app.command("arrancar", rich_help_panel=_DEEPTUTOR)(deeptutor.start)
app.command("parar", rich_help_panel=_DEEPTUTOR)(deeptutor.stop)
app.command("estado", rich_help_panel=_DEEPTUTOR)(deeptutor.status)
app.command("parches", rich_help_panel=_DEEPTUTOR)(deeptutor.patches)


def main() -> None:
    """Ejecuta la aplicación."""
    app()


if __name__ == "__main__":
    main()
