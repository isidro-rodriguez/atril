"""Comandos de backup: ``atril backup``, ``backup comprobar`` y ``backup restaurar``."""

from pathlib import Path
from typing import Annotated

import typer
from acodo.utils import parse_size
from rich.markup import escape
from rich.table import Table

from atril.backup import Archive
from atril.checks import info, ok, warning
from atril.commands._common import (
    ask_yes,
    console,
    fail_error,
    get_station,
    reporter,
    show,
    success,
)
from atril.errors import AtrilError
from atril.ops import backup as operations

backup_app = typer.Typer(
    help="Copias de seguridad comprimidas (zip o tar.xz) en una o varias carpetas.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@backup_app.callback()
def run_backup(
    ctx: typer.Context,
    no_restart: Annotated[
        bool,
        typer.Option(
            "--sin-arrancar", help="No vuelve a arrancar DeepTutor al terminar."
        ),
    ] = False,
) -> None:
    """Copia la estación (sin [bold]app/[/]) en cada destino y borra las antiguas.

    Para DeepTutor durante la copia (sus bases SQLite deben estar cerradas) y lo
    vuelve a arrancar después si estaba en marcha. La copia se comprime una vez,
    se verifica y se copia al resto de destinos; un disco desconectado se salta.
    """
    if ctx.invoked_subcommand is not None:
        return
    station = get_station(ctx)
    try:
        created = operations.create(station, reporter, restart=not no_restart)
    except AtrilError as exc:
        fail_error(exc)
    size = parse_size(created.size)
    success(
        f"Backup terminado: {created.archive.name} ({size}, {created.files} ficheros)."
    )


@backup_app.command("comprobar")
def check_backups(ctx: typer.Context) -> None:
    """Lista las copias de cada destino y verifica la más reciente.

    La verificación lee la copia entera y exige [bold]atril.toml[/], [bold]data/[/]
    y [bold]temarios/[/]; avisa si la última copia tiene más de una semana.
    """
    try:
        reports = operations.check(get_station(ctx), reporter)
    except AtrilError as exc:
        fail_error(exc)
    clean = True
    for report in reports:
        _show_archives(report.folder, report.archives)
        clean = show(report.findings) and clean
    if not clean:
        raise typer.Exit(1)


@backup_app.command("restaurar")
def restore(
    ctx: typer.Context,
    archive_path: Annotated[
        Path | None,
        typer.Argument(
            metavar="COPIA", help="Fichero de la copia; por defecto, la más reciente."
        ),
    ] = None,
    yes: Annotated[bool, typer.Option("--si", help="No pide confirmación.")] = False,
    other_path: Annotated[
        bool,
        typer.Option(
            "--nueva-ruta", help="Acepta una copia hecha desde otra ruta de estación."
        ),
    ] = False,
) -> None:
    """Restaura [bold]atril.toml[/], [bold]data/[/] y [bold]temarios/[/] de una copia.

    Extrae primero en una carpeta junto a la estación y después intercambia; lo
    que había se conserva en [bold]<estación>.previo-<fecha>[/] (bórralo tú
    cuando compruebes que todo está bien). DeepTutor debe estar parado. Si el
    intercambio falla a medias, se deshace. Una copia hecha desde otra ruta exige
    [bold]--nueva-ruta[/] (las KB guardan rutas absolutas: revísalas).
    """
    station = get_station(ctx)
    try:
        plan = operations.plan_restore(station, reporter, archive_path)
        if not yes and not ask_yes(plan.question(station)):
            raise typer.Exit(1)
        restored = operations.restore(station, plan, reporter, other_root=other_path)
    except AtrilError as exc:
        fail_error(exc)
    findings = [
        ok(f"Restaurado: {', '.join(restored.replaced)}."),
        info(f"Lo anterior: {restored.keep}."),
    ]
    if restored.blanked_keys:
        findings.append(
            warning(
                f"La copia no lleva las {restored.blanked_keys} claves de API: "
                "vuelve a escribirlas en la configuración de DeepTutor."
            )
        )
    show(findings)
    success("Restauración terminada. Comprueba con: atril estado")


# --- auxiliares ----------------------------------------------------------------


def _show_archives(folder: Path, found: list[Archive]) -> None:
    """Tabla con las últimas copias de un destino."""
    table = Table("Copia", "Tamaño", title=escape(str(folder)), title_justify="left")
    for archive in found[-10:]:
        table.add_row(escape(archive.path.name), parse_size(archive.size))
    console.print(table)
