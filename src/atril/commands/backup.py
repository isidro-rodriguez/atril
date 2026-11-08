"""Comandos de backup: ``atril backup``, ``backup comprobar`` y ``backup restaurar``."""

import shutil
import time
from pathlib import Path
from typing import Annotated

import typer
from acodo.utils import parse_size
from rich.markup import escape
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
from rich.table import Table

from atril import backup
from atril.backup import Archive, BackupError
from atril.checks import Finding, error, info, ok, warning
from atril.commands._common import ask_yes, console, fail, get_station, show, success
from atril.commands.deeptutor import launch, shutdown
from atril.config import ConfigError, load_station
from atril.config.station import Station
from atril.deeptutor import DeepTutor

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
    folders = _reachable(station)

    dt = DeepTutor(station)
    was_running = dt.installed and (dt.backend_up() or dt.frontend_up())
    if was_running:
        shutdown(dt)
    try:
        result = _create(station, folders[0])
    finally:
        if was_running and not no_restart:
            launch(dt, timeout=900)

    findings = [_verify(result.archive)]
    findings += [_copy(result.archive, folder) for folder in folders[1:]]
    findings += [warning(f"No se pudo leer {item}") for item in result.unread]
    if result.redacted:
        findings.append(
            info(f"{result.redacted} claves de API vaciadas en la copia (no viajan).")
        )
    if not show(findings, "Copias") or result.incomplete:
        fail("backup INCOMPLETO: no se borran copias antiguas. Revisa los avisos.")
    keep = station.backup.keep
    removed = [path for folder in folders for path in backup.prune(folder, keep)]
    if removed:
        show([info(f"Borradas {len(removed)} copias antiguas; se conservan {keep}.")])
    size = parse_size(result.archive.stat().st_size)
    success(
        f"Backup terminado: {result.archive.name} ({size}, {result.files} ficheros)."
    )


@backup_app.command("comprobar")
def check_backups(ctx: typer.Context) -> None:
    """Lista las copias de cada destino y verifica la más reciente.

    La verificación lee la copia entera y exige [bold]atril.toml[/], [bold]data/[/]
    y [bold]temarios/[/]; avisa si la última copia tiene más de una semana.
    """
    station = get_station(ctx)
    clean = True
    for folder in _reachable(station):
        found = backup.archives(folder)
        _show_archives(folder, found)
        if not found:
            clean = show([error(f"{folder}: sin copias.")]) and clean
            continue
        with console.status(f"Verificando {escape(found[-1].path.name)}..."):
            finding = _verify(found[-1].path)
        clean = show([finding, backup.latest_finding(found[-1])]) and clean
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
    dt = DeepTutor(station)
    if dt.installed and (dt.backend_up() or dt.frontend_up()):
        fail("DeepTutor está en marcha; páralo antes con: atril parar")
    chosen = archive_path or _latest(station)
    if not chosen.is_file():
        fail(f"no existe la copia {chosen}.")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    staging = station.root.with_name(f"{station.root.name}.restaurar-{stamp}")
    keep = station.root.with_name(f"{station.root.name}.previo-{stamp}")
    for folder in (staging, keep):
        if folder.exists():
            fail(f"{folder} ya existe; muévelo o bórralo antes de restaurar.")
    question = (
        f"Se sustituirán atril.toml, data/ y temarios/ de {station.root} por "
        f"{chosen.name}. Lo actual se guardará en {keep.name}. ¿Continuar?"
    )
    if not yes and not ask_yes(question):
        raise typer.Exit(1)
    try:
        with console.status(f"Extrayendo {escape(chosen.name)}..."):
            manifest = backup.extract(chosen, staging)
        source = str(manifest.get("estacion", ""))
        if not _same_root(source, station.root) and not other_path:
            fail(
                f"la copia se hizo desde {source or '?'}, no desde {station.root}; "
                "si es lo que quieres, repite con --nueva-ruta."
            )
        try:
            load_station(staging)
        except ConfigError as exc:
            fail(f"la copia no contiene una estación válida: {exc}")
        replaced = backup.swap_in(station, staging, keep)
    except BackupError as exc:
        fail(str(exc))
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    findings = [
        ok(f"Restaurado: {', '.join(replaced)}."),
        info(f"Lo anterior: {keep}."),
    ]
    if manifest.get("claves_vaciadas"):
        findings.append(
            warning(
                f"La copia no lleva las {manifest['claves_vaciadas']} claves de API: "
                "vuelve a escribirlas en la configuración de DeepTutor."
            )
        )
    show(findings)
    success("Restauración terminada. Comprueba con: atril estado")


# --- auxiliares ----------------------------------------------------------------


def _reachable(station: Station) -> list[Path]:
    """Destinos accesibles; un disco desconectado se salta con un aviso."""
    available = []
    for folder in station.backup.destinations:
        if backup.is_reachable(folder):
            available.append(folder)
        else:
            show([warning(f"{folder}: no está accesible; ¿disco desconectado?")])
    if not available:
        fail("ningún destino de backup accesible.")
    return available


def _create(station: Station, folder: Path) -> backup.Result:
    """Crea la copia con barra de avance."""
    total = sum(_size(path) for path, _ in backup.station_files(station))
    with Progress(
        TextColumn("[bold]Comprimiendo[/]"),
        BarColumn(),
        DownloadColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("", total=total)
        try:
            return backup.create(
                station, folder, lambda done: progress.advance(task, done)
            )
        except BackupError as exc:
            fail(str(exc))


def _size(path: Path) -> int:
    """Tamaño de un fichero; 0 si no se puede leer (se avisará al copiarlo)."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _verify(archive: Path) -> Finding:
    """Lee la copia entera y la convierte en una comprobación."""
    try:
        backup.verify(archive)
    except BackupError as exc:
        return error(str(exc))
    return ok(f"{archive} verificada.")


def _copy(archive: Path, folder: Path) -> Finding:
    """Lleva la copia ya verificada a otro destino (``.part`` y renombrado)."""
    target = folder / archive.name
    partial = target.with_name(target.name + ".part")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, partial)
        partial.replace(target)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        return error(f"{folder}: no se pudo copiar ({exc}).")
    return ok(f"{target} copiada.")


def _latest(station: Station) -> Path:
    """Copia más reciente de todos los destinos accesibles."""
    found = [a for folder in _reachable(station) for a in backup.archives(folder)]
    if not found:
        fail("no hay copias en los destinos.")
    return max(found, key=lambda archive: archive.stamp).path


def _show_archives(folder: Path, found: list[Archive]) -> None:
    """Tabla con las últimas copias de un destino."""
    table = Table("Copia", "Tamaño", title=escape(str(folder)), title_justify="left")
    for archive in found[-10:]:
        table.add_row(escape(archive.path.name), parse_size(archive.size))
    console.print(table)


def _same_root(source: str, root: Path) -> bool:
    """La copia se hizo desde esta ruta (sin distinguir mayúsculas ni barras)."""

    def norm(text: str) -> str:
        return text.replace("\\", "/").rstrip("/").lower()

    return norm(source) == norm(str(root))
