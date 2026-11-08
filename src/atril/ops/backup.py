"""Copias de seguridad: crear, comprobar y restaurar la estación."""

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from atril import backup
from atril.backup import Archive, BackupError, SwapError
from atril.checks import Finding, Level, error, info, ok, warning
from atril.config import ConfigError, load_station
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError, CancelledError
from atril.lock import station_lock
from atril.ops import Reporter, service

RESTART_TIMEOUT = 900
"""Segundos de espera al volver a arrancar DeepTutor tras la copia."""


@dataclass(frozen=True, slots=True)
class Created:
    """Copia creada, verificada y repartida."""

    archive: Path
    files: int
    size: int
    removed: int
    """Copias antiguas borradas en todos los destinos."""


@dataclass(frozen=True, slots=True)
class FolderReport:
    """Copias de un destino y verificación de la más reciente."""

    folder: Path
    archives: list[Archive]
    findings: list[Finding]


@dataclass(frozen=True, slots=True)
class RestorePlan:
    """Restauración preparada, pendiente de confirmar."""

    archive: Path
    staging: Path
    """Carpeta temporal de extracción, junto a la estación."""
    keep: Path
    """Carpeta donde queda lo que hay ahora."""

    def question(self, station: Station) -> str:
        """Pregunta de confirmación para el usuario."""
        return (
            f"Se sustituirán atril.toml, data/ y temarios/ de {station.root} por "
            f"{self.archive.name}. Lo actual se guardará en {self.keep.name}. "
            "¿Continuar?"
        )


@dataclass(frozen=True, slots=True)
class Restored:
    """Resultado de una restauración."""

    replaced: list[str]
    keep: Path
    blanked_keys: int
    """Claves de API que la copia no lleva y hay que volver a escribir."""


def reachable(station: Station, reporter: Reporter) -> list[Path]:
    """Destinos accesibles; un disco desconectado se salta con un aviso.

    Raises:
        AtrilError: Si no hay ninguno.
    """
    available = []
    for folder in station.backup.destinations:
        if backup.is_reachable(folder):
            available.append(folder)
        else:
            reporter.show(
                [warning(f"{folder}: no está accesible; ¿disco desconectado?")]
            )
    if not available:
        raise AtrilError("ningún destino de backup accesible.")
    return available


def create(
    station: Station,
    reporter: Reporter,
    *,
    restart: bool = True,
    cancel: threading.Event | None = None,
) -> Created:
    """Copia la estación en cada destino y borra las antiguas.

    Para DeepTutor durante la copia (SQLite) y lo vuelve a arrancar si estaba en
    marcha y ``restart``. La copia se comprime una vez, se verifica y se copia al
    resto de destinos. Si falta algún fichero o falla una copia, no se borra nada.

    Raises:
        AtrilError: Si la copia no se puede hacer o queda incompleta.
        CancelledError: Si se activa ``cancel`` mientras se comprime.
    """
    with station_lock(station, "copia de seguridad"):
        folders = reachable(station, reporter)
        dt = DeepTutor(station)
        was_running = dt.installed and (dt.backend_up() or dt.frontend_up())
        if was_running:
            service.stop(dt, reporter)
        try:
            result = _compress(station, folders[0], reporter, cancel)
        finally:
            if was_running and restart:
                service.start(dt, reporter, timeout=RESTART_TIMEOUT)

        findings = [warning(f"No se pudo leer {item}") for item in result.unread]
        findings += [
            warning(f"No se copia el enlace {item} (podría salir de la estación).")
            for item in result.skipped
        ]
        if result.incomplete:
            findings.append(
                error(
                    f"{result.archive.name}: incompleta; se guarda aparte, no cuenta "
                    "para la retención ni se ofrece para restaurar."
                )
            )
        else:
            findings.append(verify_finding(result.archive))
            findings += [copy_to(result.archive, folder) for folder in folders[1:]]
        if result.redacted:
            findings.append(
                info(
                    f"{result.redacted} claves de API vaciadas en la copia (no viajan)."
                )
            )
        reporter.show(findings, "Copias")
        if result.incomplete or any(f.level is Level.ERROR for f in findings):
            raise AtrilError(
                "backup INCOMPLETO: no se borran copias antiguas. Revisa los avisos."
            )
        keep = station.backup.keep
        removed = [path for folder in folders for path in backup.prune(folder, keep)]
        if removed:
            reporter.show(
                [info(f"Borradas {len(removed)} copias antiguas; se conservan {keep}.")]
            )
        return Created(
            result.archive, result.files, result.archive.stat().st_size, len(removed)
        )


class OtherRootError(AtrilError):
    """La copia se hizo desde otra ruta de estación; hay que aceptarlo expresamente."""


def listing(station: Station, reporter: Reporter) -> list[FolderReport]:
    """Copias de cada destino accesible, sin verificarlas (rápido)."""
    folders = reachable(station, reporter)
    return [FolderReport(folder, backup.archives(folder), []) for folder in folders]


def check(station: Station, reporter: Reporter) -> list[FolderReport]:
    """Copias de cada destino accesible, con la más reciente verificada entera."""
    reports = []
    for folder in reachable(station, reporter):
        found = backup.archives(folder)
        if not found:
            findings = [error(f"{folder}: sin copias.")]
        else:
            with reporter.busy(f"Verificando {found[-1].path.name}..."):
                findings = [verify_finding(found[-1].path)]
            findings.append(backup.latest_finding(found[-1]))
        if broken := backup.incomplete_archives(folder):
            findings.append(
                warning(
                    f"{folder}: {len(broken)} copias incompletas (no se restauran); "
                    "bórralas cuando quieras."
                )
            )
        reports.append(FolderReport(folder, found, findings))
    return reports


def plan_restore(
    station: Station, reporter: Reporter, archive: Path | None = None
) -> RestorePlan:
    """Prepara la restauración de ``archive`` (por defecto, la copia más reciente).

    Raises:
        AtrilError: Si DeepTutor está en marcha, no hay copia o las carpetas de
            trabajo ya existen.
    """
    _require_stopped(station)
    chosen = archive or _latest(station, reporter)
    if not chosen.is_file():
        raise AtrilError(f"no existe la copia {chosen}.")
    if backup.INCOMPLETE in chosen.name:
        raise AtrilError(f"{chosen.name} es una copia incompleta; elige otra.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    staging = station.root.with_name(f"{station.root.name}.restaurar-{stamp}")
    keep = station.root.with_name(f"{station.root.name}.previo-{stamp}")
    for folder in (staging, keep):
        if folder.exists():
            raise AtrilError(
                f"{folder} ya existe; muévelo o bórralo antes de restaurar."
            )
    return RestorePlan(chosen, staging, keep)


def restore(
    station: Station,
    plan: RestorePlan,
    reporter: Reporter,
    *,
    other_root: bool = False,
) -> Restored:
    """Extrae la copia junto a la estación y la intercambia con lo actual.

    Lo que había queda en ``plan.keep``; si el intercambio falla a medias, se
    deshace. Una copia hecha desde otra ruta exige ``other_root``.

    Raises:
        AtrilError: Si la copia no es válida, es de otra ruta o falla el intercambio.
    """
    with station_lock(station, "restauración"):
        _require_stopped(station)
        keep_staging = False
        try:
            with reporter.busy(f"Extrayendo {plan.archive.name}..."):
                manifest = backup.extract(plan.archive, plan.staging)
            source = manifest.station
            if not same_root(source, station.root) and not other_root:
                raise OtherRootError(
                    f"la copia se hizo desde {source or '?'}, no desde "
                    f"{station.root}; si es lo que quieres, acepta la nueva ruta "
                    "(--nueva-ruta)."
                )
            try:
                load_station(plan.staging)
            except ConfigError as exc:
                raise AtrilError(
                    f"la copia no contiene una estación válida: {exc}"
                ) from exc
            _require_stopped(station)  # justo antes de tocar la estación
            try:
                replaced = backup.swap_in(station, plan.staging, plan.keep)
            except SwapError as exc:
                keep_staging = exc.uncertain  # estado incierto: no se borra nada
                raise
        finally:
            if plan.staging.exists() and not keep_staging:
                shutil.rmtree(plan.staging, ignore_errors=True)
    return Restored(replaced, plan.keep, manifest.blanked_keys)


def _require_stopped(station: Station) -> None:
    """Exige DeepTutor parado (sus bases SQLite no pueden estar abiertas).

    Raises:
        AtrilError: Si responde el backend o el frontend.
    """
    dt = DeepTutor(station)
    if dt.installed and (dt.backend_up() or dt.frontend_up()):
        raise AtrilError("DeepTutor está en marcha; páralo antes de restaurar.")


def verify_finding(archive: Path) -> Finding:
    """Lee la copia entera y la convierte en una comprobación."""
    try:
        backup.verify(archive)
    except BackupError as exc:
        return error(str(exc))
    return ok(f"{archive} verificada.")


def copy_to(archive: Path, folder: Path) -> Finding:
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
    try:
        backup.verify(target)
    except BackupError as exc:
        return error(f"{folder}: la copia no se ha verificado ({exc}).")
    return ok(f"{target} copiada y verificada.")


def same_root(source: str, root: Path) -> bool:
    """La copia se hizo desde esta ruta (sin distinguir mayúsculas ni barras)."""

    def norm(text: str) -> str:
        return text.replace("\\", "/").rstrip("/").lower()

    return norm(source) == norm(str(root))


def _compress(
    station: Station,
    folder: Path,
    reporter: Reporter,
    cancel: threading.Event | None,
) -> backup.Result:
    """Crea la copia con avance por bytes; se cancela entre fichero y fichero."""
    total = sum(_size(path) for path, _ in backup.station_files(station))
    with reporter.progress("Comprimiendo", total) as advance:

        def step(done: int) -> None:
            if cancel is not None and cancel.is_set():
                raise CancelledError("copia cancelada; no se ha guardado nada.")
            advance(done)

        return backup.create(station, folder, step)


def _size(path: Path) -> int:
    """Tamaño de un fichero; 0 si no se puede leer (se avisará al copiarlo)."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _latest(station: Station, reporter: Reporter) -> Path:
    """Copia más reciente de todos los destinos accesibles."""
    found = [
        a for folder in reachable(station, reporter) for a in backup.archives(folder)
    ]
    if not found:
        raise AtrilError("no hay copias en los destinos.")
    return max(found, key=lambda archive: archive.stamp).path
