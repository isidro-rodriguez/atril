"""Comandos de configuración: ``atril validar``."""

import typer
from rich.markup import escape
from rich.table import Table

from atril.checks import warning
from atril.commands._common import console, fail, get_station, show, success
from atril.config import ConfigError, load_syllabi


def validate(ctx: typer.Context) -> None:
    """Valida [bold]atril.toml[/] y el [bold]temario.toml[/] de cada temario."""
    station = get_station(ctx)
    try:
        syllabi, warnings = load_syllabi(station.syllabi_dir)
    except ConfigError as exc:
        fail(str(exc))

    console.print(f"Estación: [cyan]{escape(str(station.root))}[/]")
    if syllabi:
        table = Table("Temario", "Nombre")
        table.add_column("KB", justify="right")
        table.add_column("Fuentes", justify="right")
        for syllabus in syllabi:
            table.add_row(
                syllabus.id,
                escape(syllabus.name),
                str(len(syllabus.knowledge_bases)),
                str(len(syllabus.sources)),
            )
        console.print(table)
    show(warning(message) for message in warnings)
    success("Configuración válida.")
