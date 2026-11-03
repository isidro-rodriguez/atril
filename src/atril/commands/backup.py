"""Comandos de backup: ``atril backup``, ``backup comprobar`` y ``backup restaurar``."""

import shutil
import time
from typing import Annotated

import typer
from acodo.utils import parse_size
from rich.markup import escape
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
from rich.table import Table

from atril import backup
from atril.backup import BackupError, Restic, Snapshot, Summary
from atril.checks import Finding, Level, error, info, ok, warning
from atril.commands._common import console, fail, get_station, show, success
from atril.commands.deeptutor import launch, shutdown
from atril.config.station import BackupTarget, Station
from atril.deeptutor import DeepTutor

backup_app = typer.Typer(
    help="Copias de seguridad con restic (disco externo y Google Drive).",
    invoke_without_command=True,
    rich_markup_mode="rich",
)

Targets = Annotated[
    list[str] | None,
    typer.Option("--destino", "-d", help="Destino de atril.toml; por defecto, todos."),
]


@backup_app.callback()
def run_backup(
    ctx: typer.Context,
    targets: Targets = None,
    no_restart: Annotated[
        bool,
        typer.Option(
            "--sin-arrancar", help="No vuelve a arrancar DeepTutor al terminar."
        ),
    ] = False,
) -> None:
    """Copia la estación (sin [bold]app/[/]) en cada destino y aplica la retención.

    Para DeepTutor durante la copia (sus bases SQLite deben estar cerradas) y lo
    vuelve a arrancar después si estaba en marcha. Un disco externo
    desconectado se salta con un aviso.
    """
    if ctx.invoked_subcommand is not None:
        return
    station = get_station(ctx)
    executable = _restic()
    selected = _select(station, targets)
    reachable = _reachable(selected, explicit=bool(targets))

    dt = DeepTutor(station)
    was_running = dt.installed and (dt.backend_up() or dt.frontend_up())
    if was_running:
        shutdown(dt)
    try:
        bundles = _bundle_findings(station)
        show(bundles, "Repos de git")
        results = [_backup_one(station, target, executable) for target in reachable]
    finally:
        if was_running and not no_restart:
            launch(dt, timeout=900)
    _show_summaries(results)
    incomplete = [t.name for t, s in results if s.incomplete]
    if incomplete or any(f.level is Level.ERROR for f in bundles):
        problems = [f"faltan ficheros en {', '.join(incomplete)}"] if incomplete else []
        if any(f.level is Level.ERROR for f in bundles):
            problems.append("algún repo de repos_git no se ha empaquetado")
        fail(f"backup INCOMPLETO: {'; '.join(problems)}. Revisa los avisos.")
    success("Backup terminado.")


@backup_app.command("comprobar")
def check_backups(
    ctx: typer.Context,
    targets: Targets = None,
    read_data: Annotated[
        str | None,
        typer.Option(
            "--datos",
            help="Lee también esta parte de los datos para verificarlos (p. ej. 5%).",
        ),
    ] = None,
) -> None:
    """Verifica la integridad de cada repositorio y lista sus últimos snapshots."""
    station = get_station(ctx)
    executable = _restic()
    clean = True
    for target in _reachable(_select(station, targets), explicit=bool(targets)):
        restic = Restic(target, executable)
        with console.status(f"Comprobando {escape(target.name)}..."):
            try:
                restic.check(read_data)
                snapshots = restic.snapshots()
                finding = ok(f"{target.name}: repositorio correcto.")
            except BackupError as exc:
                snapshots = []
                finding = error(str(exc))
        clean = show([finding], target.name) and clean
        _show_snapshots(snapshots[-5:])
    if not clean:
        raise typer.Exit(1)


@backup_app.command("restaurar")
def restore(
    ctx: typer.Context,
    target_name: Annotated[
        str, typer.Option("--destino", "-d", help="Destino del que restaurar.")
    ],
    snapshot: Annotated[
        str, typer.Option("--snapshot", "-s", help="Id del snapshot.")
    ] = "latest",
    yes: Annotated[bool, typer.Option("--si", help="No pide confirmación.")] = False,
    other_path: Annotated[
        bool,
        typer.Option(
            "--forzar-otra-ruta",
            help="Restaura un snapshot hecho desde otra ruta (las KB guardan rutas "
            "absolutas y habrá que revisarlas).",
        ),
    ] = False,
) -> None:
    """Restaura [bold]atril.toml[/], [bold]data/[/] y [bold]temarios/[/] en su ruta.

    Restaura primero en una carpeta junto a la estación y después intercambia;
    lo que había se conserva en [bold]<estación>.previo-<fecha>[/] (bórralo tú
    cuando compruebes que todo está bien). DeepTutor debe estar parado.
    """
    station = get_station(ctx)
    executable = _restic()
    (target,) = _reachable(_select(station, [target_name]), explicit=True)
    dt = DeepTutor(station)
    if dt.installed and (dt.backend_up() or dt.frontend_up()):
        fail("DeepTutor está en marcha; páralo antes con: atril parar")

    restic = Restic(target, executable)
    try:
        snapshots = restic.snapshots()
    except BackupError as exc:
        fail(str(exc))
    chosen = snapshots[-1] if snapshot == "latest" and snapshots else None
    if snapshot != "latest":
        chosen = next((s for s in snapshots if s.short_id.startswith(snapshot)), None)
    if chosen is None:
        fail(f"no hay snapshot {snapshot!r} en {target.name}.")
    _show_snapshots([chosen])
    findings = _path_findings(station, chosen)
    show(findings)
    if any(f.level is Level.WARNING for f in findings) and not other_path:
        fail(
            "el snapshot es de otra ruta; si es lo que quieres, repite con "
            "--forzar-otra-ruta."
        )

    stamp = time.strftime("%Y%m%d-%H%M%S")
    staging = station.root.with_name(f"{station.root.name}.restaurar-{stamp}")
    keep = station.root.with_name(f"{station.root.name}.previo-{stamp}")
    message = (
        f"Se sustituirán atril.toml, data/ y temarios/ de {station.root} por el "
        f"snapshot {chosen.short_id}. Lo actual se guardará en {keep.name}. ¿Continuar?"
    )
    if not yes and not typer.confirm(message):
        raise typer.Exit(1)

    try:
        with console.status(
            f"Restaurando {chosen.short_id} en {escape(staging.name)}..."
        ):
            restic.restore(chosen.short_id, staging)
        restored = backup.find_restored_root(staging)
        if restored is None:
            fail(f"el snapshot no contiene una estación reconocible (mira {staging}).")
        replaced = backup.swap_in(station, restored, keep)
    except BackupError as exc:
        fail(str(exc))
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    show(
        [
            ok(f"Restaurado: {', '.join(replaced)}."),
            info(f"Lo anterior está en {keep}."),
        ]
    )
    success("Restauración terminada. Comprueba con: atril estado")


# --- auxiliares ----------------------------------------------------------------


def _restic() -> str:
    """Ruta de restic; termina con error si falta él o la contraseña."""
    executable = shutil.which("restic")
    if executable is None:
        fail(
            "no se encuentra restic en el PATH (Windows: winget install restic.restic)."
        )
    if not backup.password_configured():
        fail(
            "restic necesita la contraseña del repositorio en RESTIC_PASSWORD, "
            "RESTIC_PASSWORD_FILE o RESTIC_PASSWORD_COMMAND (nunca en atril.toml)."
        )
    return executable


def _select(station: Station, names: list[str] | None) -> list[BackupTarget]:
    """Destinos pedidos (o todos); termina si alguno no existe en atril.toml."""
    targets = list(station.backup.targets)
    if not names:
        return targets
    known = {target.name: target for target in targets}
    unknown = [name for name in names if name not in known]
    if unknown:
        fail(
            f"destinos desconocidos: {', '.join(unknown)} "
            f"(atril.toml tiene: {', '.join(known)})."
        )
    return [known[name] for name in names]


def _reachable(targets: list[BackupTarget], *, explicit: bool) -> list[BackupTarget]:
    """Destinos accesibles; un disco desconectado se salta (o falla si se pidió)."""
    available, skipped = [], []
    for target in targets:
        (available if backup.is_reachable(target) else skipped).append(target)
    uses_rclone = any(target.repo.startswith("rclone:") for target in available)
    if uses_rclone and shutil.which("rclone") is None:
        fail("hay destinos rclone pero rclone no está en el PATH.")
    for target in skipped:
        message = (
            f"{target.name}: no está accesible ({target.repo}); ¿disco desconectado?"
        )
        if explicit:
            fail(message)
        show([warning(message)])
    if not available:
        fail("ningún destino accesible.")
    return available


def _bundle_findings(station: Station) -> list[Finding]:
    """Crea los git bundle y los convierte en comprobaciones."""
    if not backup.git_repos(station):
        return [info("No hay repos de git que empaquetar.")]
    if shutil.which("git") is None:
        return [warning("git no está en el PATH: se copia sin bundles.")]
    findings = []
    for result in backup.make_bundles(station):
        if not result.error:
            findings.append(ok(f"{result.name}.bundle"))
        elif result.required:
            findings.append(error(f"{result.name}: {result.error}"))
        else:
            findings.append(warning(f"{result.name}: {result.error}"))
    return findings


def _backup_one(
    station: Station, target: BackupTarget, executable: str
) -> tuple[BackupTarget, Summary]:
    """Backup y retención en un destino, con barra de avance."""
    restic = Restic(target, executable)
    keep = station.backup.retention
    try:
        if restic.ensure_repository():
            show([info(f"{target.name}: repositorio creado en {target.repo}.")])
        with Progress(
            TextColumn(f"[bold]{escape(target.name)}[/]"),
            BarColumn(),
            DownloadColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("", total=None)

            def update(fraction: float, done: int, total: int) -> None:
                progress.update(task, completed=done, total=total or None)

            summary = restic.backup(backup.backup_paths(station), update)
        if summary.incomplete:
            # Un snapshot incompleto no debe desplazar a uno completo en la
            # retención: no se aplica hasta el siguiente backup correcto.
            show(
                [
                    warning(f"{target.name}: no se pudo leer {item}")
                    for item in summary.unread
                ]
                + [
                    warning(
                        f"{target.name}: snapshot incompleto; retención no aplicada."
                    )
                ]
            )
            return target, summary
        with console.status(f"Aplicando la retención en {escape(target.name)}..."):
            restic.forget(keep.daily, keep.weekly, keep.monthly)
    except BackupError as exc:
        fail(str(exc))
    return target, summary


def _show_summaries(results: list[tuple[BackupTarget, Summary]]) -> None:
    """Tabla con el resultado de cada destino."""
    table = Table("Destino", "Snapshot", "Nuevos", "Cambiados", "Añadido", "Duración")
    table.title = "Backup"
    table.title_justify = "left"
    for target, summary in results:
        table.add_row(
            escape(target.name),
            summary.snapshot,
            str(summary.files_new),
            str(summary.files_changed),
            parse_size(summary.data_added),
            f"{summary.seconds:.0f} s",
        )
    console.print(table)


def _show_snapshots(snapshots: list[Snapshot]) -> None:
    """Tabla de snapshots."""
    if not snapshots:
        show([info("Sin snapshots de atril.")])
        return
    table = Table("Snapshot", "Fecha", "Equipo", "Rutas")
    for item in snapshots:
        table.add_row(
            item.short_id,
            item.time.replace("T", " "),
            escape(item.hostname),
            escape(", ".join(item.paths)),
        )
    console.print(table)


def _path_findings(station: Station, snapshot: Snapshot) -> list[Finding]:
    """Avisa si el snapshot es de otra ruta (kb_config.json guarda rutas absolutas)."""
    roots = {str(_parent(path)) for path in snapshot.paths}
    here = str(station.root).replace("\\", "/").lower()
    if roots and all(
        root.replace("\\", "/").lower().rstrip("/") == here for root in roots
    ):
        return [ok("El snapshot es de esta misma ruta.")]
    return [
        warning(
            f"El snapshot se hizo desde {', '.join(sorted(roots))}, no desde "
            f"{station.root}: las rutas absolutas de las KB (kb_config.json) no "
            "coincidirán."
        )
    ]


def _parent(path: str) -> str:
    """Carpeta que contiene una ruta de snapshot (formato POSIX o Windows de restic)."""
    normalized = path.replace("\\", "/").rstrip("/")
    parent = normalized.rsplit("/", 1)[0]
    # restic en Windows guarda /D/ruta: equivale a D:/ruta.
    if (
        len(parent) > 2
        and parent[0] == "/"
        and parent[2] == "/"
        and parent[1].isalpha()
    ):
        parent = f"{parent[1]}:{parent[2:]}"
    return parent
