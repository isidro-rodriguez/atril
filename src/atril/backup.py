"""Copias de seguridad de la estación con restic.

Se copian ``atril.toml``, ``data/`` y ``temarios/`` (no ``app/``, que se
reconstruye con ``atril instalar``), más un *git bundle* de cada repo (el git de
cada temario y ``[backup] repos_git``) dentro de ``data/atril/bundles/``.

La contraseña de restic viene del entorno (``RESTIC_PASSWORD``,
``RESTIC_PASSWORD_FILE`` o ``RESTIC_PASSWORD_COMMAND``), nunca de ``atril.toml``.
"""

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atril.config.station import BackupTarget, Station

PASSWORD_VARIABLES = (
    "RESTIC_PASSWORD",
    "RESTIC_PASSWORD_FILE",
    "RESTIC_PASSWORD_COMMAND",
)
"""Variables con las que restic obtiene la contraseña del repositorio."""

TAG = "atril"
"""Etiqueta de los snapshots de atril."""

EXCLUDES = ("*.part", "*.nuevo")
"""Descargas a medias de atril: no se copian."""

EXIT_NO_REPOSITORY = 10
"""Código de restic (>= 0.17) cuando el repositorio no existe."""

EXIT_WRONG_PASSWORD = 12
"""Código de restic cuando la contraseña no abre el repositorio."""

EXIT_INCOMPLETE = 3
"""Código de ``restic backup``: snapshot creado, pero faltan ficheros ilegibles."""

REMOTE_PREFIXES = ("rclone:", "sftp:", "s3:", "b2:", "azure:", "gs:", "rest:", "swift:")
"""Repositorios que no son una carpeta local."""


class BackupError(Exception):
    """Fallo de restic o de la preparación del backup; mensaje en español."""


@dataclass(frozen=True, slots=True)
class Summary:
    """Resumen de un ``restic backup``."""

    snapshot: str
    files_new: int
    files_changed: int
    data_added: int
    seconds: float
    unread: tuple[str, ...] = ()
    """Errores de lectura: el snapshot existe pero está incompleto."""

    @property
    def incomplete(self) -> bool:
        """``True`` si restic no pudo leer algún fichero."""
        return bool(self.unread)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Snapshot de un repositorio."""

    short_id: str
    time: str
    paths: tuple[str, ...]
    hostname: str


Progress = Callable[[float, int, int], None]
"""Avance: fracción completada, bytes hechos y bytes totales."""


def is_local(target: BackupTarget) -> bool:
    """El repositorio es una carpeta (p. ej. un disco externo)."""
    return not target.repo.startswith(REMOTE_PREFIXES)


def is_reachable(target: BackupTarget) -> bool:
    """Un repositorio local está accesible si existe su carpeta padre (disco conectado).

    Los remotos se dan por accesibles: restic informará si no lo son.
    """
    return not is_local(target) or Path(target.repo).parent.is_dir()


def password_configured(env: dict[str, str] | None = None) -> bool:
    """Hay alguna forma de contraseña para restic en el entorno."""
    environ = os.environ if env is None else env
    return any(environ.get(name) for name in PASSWORD_VARIABLES)


def backup_paths(station: Station) -> list[Path]:
    """Lo que se copia de la estación (solo lo que existe)."""
    paths = [station.root / "atril.toml", station.data_dir, station.syllabi_dir]
    return [path for path in paths if path.exists()]


def bundles_dir(station: Station) -> Path:
    """Carpeta de los git bundle (dentro de ``data/``, así entran en el snapshot)."""
    return station.data_dir / "atril" / "bundles"


def git_repos(station: Station) -> dict[str, Path]:
    """Repos de git a empaquetar: cada temario con ``.git`` y ``repos_git``."""
    repos: dict[str, Path] = {}
    if station.syllabi_dir.is_dir():
        for folder in sorted(station.syllabi_dir.iterdir()):
            if (folder / ".git").exists():
                repos[f"temario-{folder.name}"] = folder
    for repo in station.backup.git_repos:
        repos[f"repo-{repo.name}"] = repo
    return repos


class Restic:
    """Llamadas a restic para un repositorio."""

    def __init__(self, target: BackupTarget, executable: str = "restic") -> None:
        """Prepara las llamadas al repositorio de ``target``."""
        self.target = target
        self.executable = executable

    def _command(self, *args: str) -> list[str]:
        """Comando completo de restic con el repositorio."""
        return [self.executable, "-r", self.target.repo, *args]

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Ejecuta restic capturando la salida."""
        result = subprocess.run(
            self._command(*args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if check and result.returncode != 0:
            raise BackupError(self._explain(result))
        return result

    def _explain(self, result: subprocess.CompletedProcess[str]) -> str:
        """Mensaje de error de restic, con pista para los casos conocidos."""
        if result.returncode == EXIT_WRONG_PASSWORD:
            return f"{self.target.name}: la contraseña no abre el repositorio."
        if result.returncode == EXIT_NO_REPOSITORY:
            return f"{self.target.name}: el repositorio no existe ({self.target.repo})."
        lines = [line for line in result.stderr.strip().splitlines() if line.strip()]
        detail = lines[-1] if lines else f"código {result.returncode}"
        return f"{self.target.name}: {detail}"

    def ensure_repository(self) -> bool:
        """Inicializa el repositorio si no existe.

        Returns:
            ``True`` si se ha creado ahora.
        """
        result = self._run("cat", "config", check=False)
        if result.returncode == 0:
            return False
        if result.returncode != EXIT_NO_REPOSITORY:
            raise BackupError(self._explain(result))
        self._run("init")
        return True

    def backup(self, paths: list[Path], progress: Progress | None = None) -> Summary:
        """``restic backup`` con avance; devuelve el resumen."""
        args = ["backup", "--json", "--tag", TAG]
        for pattern in EXCLUDES:
            args += ["--exclude", pattern]
        command = self._command(*args, *(str(path) for path in paths))
        summary: dict[str, Any] = {}
        errors: list[str] = []
        # stderr a un fichero: con dos tuberías, restic podría bloquearse si
        # llenase la de stderr mientras se lee stdout.
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in process.stdout or ():
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                kind = message.get("message_type")
                if kind == "status" and progress:
                    progress(
                        float(message.get("percent_done", 0)),
                        int(message.get("bytes_done", 0)),
                        int(message.get("total_bytes", 0)),
                    )
                elif kind == "summary":
                    summary = message
                elif kind == "error":
                    errors.append(_error_text(message))
            process.wait()
            log.seek(0)
            stderr = log.read()
        code = process.returncode
        if code not in {0, EXIT_INCOMPLETE} or not summary:
            detail = (errors or stderr.strip().splitlines() or [f"código {code}"])[-1]
            raise BackupError(f"{self.target.name}: {detail}")
        unread = tuple(errors) if code == EXIT_INCOMPLETE else ()
        if code == EXIT_INCOMPLETE and not unread:
            unread = tuple((stderr.strip().splitlines() or ["ficheros sin leer"])[-1:])
        return Summary(
            snapshot=str(summary.get("snapshot_id", ""))[:8],
            files_new=int(summary.get("files_new", 0)),
            files_changed=int(summary.get("files_changed", 0)),
            data_added=int(summary.get("data_added", 0)),
            seconds=float(summary.get("total_duration", 0)),
            unread=unread,
        )

    def forget(self, daily: int, weekly: int, monthly: int) -> None:
        """Aplica la retención y borra los datos que ya no usa ningún snapshot."""
        self._run(
            "forget",
            "--tag",
            TAG,
            "--keep-daily",
            str(daily),
            "--keep-weekly",
            str(weekly),
            "--keep-monthly",
            str(monthly),
            "--prune",
        )

    def snapshots(self) -> list[Snapshot]:
        """Snapshots de atril, del más antiguo al más reciente."""
        data = json.loads(self._run("snapshots", "--json", "--tag", TAG).stdout or "[]")
        return [
            Snapshot(
                short_id=str(item.get("short_id", item.get("id", ""))[:8]),
                time=str(item.get("time", ""))[:19],
                paths=tuple(item.get("paths", [])),
                hostname=str(item.get("hostname", "")),
            )
            for item in data or []
        ]

    def check(self, read_data: str | None = None) -> None:
        """``restic check``; con ``read_data`` (p. ej. ``5%``) lee esa parte."""
        args = ["check"]
        if read_data:
            args.append(f"--read-data-subset={read_data}")
        self._run(*args)

    def restore(self, snapshot: str, target: Path) -> None:
        """Restaura un snapshot en ``target`` (con la estructura de la estación)."""
        self._run("restore", snapshot, "--target", str(target))


@dataclass(frozen=True, slots=True)
class BundleResult:
    """Resultado de empaquetar un repo de git."""

    name: str
    error: str = ""
    """Vacío si el bundle se ha creado."""
    required: bool = False
    """Repo declarado en ``repos_git``: si falla, el backup queda incompleto."""


def make_bundles(station: Station, git: str = "git") -> list[BundleResult]:
    """Crea un git bundle de cada repo.

    Un fallo no detiene el resto: se anota en el resultado. El git de un temario
    sin commits no importa; un repo de ``repos_git`` que falla deja el backup
    incompleto.
    """
    folder = bundles_dir(station)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    declared = set(station.backup.git_repos)
    for name, repo in git_repos(station).items():
        target = folder / f"{name}.bundle"
        result = subprocess.run(
            [git, "-C", str(repo), "bundle", "create", str(target), "--all"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        lines = result.stderr.strip().splitlines()
        failure = "" if result.returncode == 0 else (lines[-1] if lines else "error")
        results.append(BundleResult(name, failure, required=repo in declared))
    return results


def find_restored_root(target: Path) -> Path | None:
    """Carpeta restaurada con la estructura de una estación (``atril.toml`` o ``data``).

    restic deja la estructura relativa al ancestro común de las rutas copiadas,
    pero se busca a algo de profundidad por si cambia.
    """
    candidates = [target, *sorted(p for p in target.rglob("*") if p.is_dir())]
    for folder in candidates:
        looks_like_station = (folder / "atril.toml").is_file() or (
            folder / "data"
        ).is_dir()
        if looks_like_station and len(folder.relative_to(target).parts) <= 6:
            return folder
    return None


RESTORED_ITEMS = ("atril.toml", "data", "temarios")
"""Lo que una restauración sustituye en la estación."""


def swap_in(station: Station, restored: Path, keep: Path) -> list[str]:
    """Sustituye ``atril.toml``, ``data/`` y ``temarios/`` por los restaurados.

    Lo que había se mueve a ``keep`` (no se borra nada). Si un movimiento falla
    (p. ej. un fichero bloqueado en Windows), se deshacen los anteriores y la
    estación queda como estaba.

    Returns:
        Los elementos sustituidos.

    Raises:
        BackupError: Si el intercambio falla; el mensaje dice si se ha deshecho.
    """
    keep.mkdir(parents=True, exist_ok=False)
    done: list[tuple[Path, Path]] = []
    replaced = []
    try:
        for name in RESTORED_ITEMS:
            source = restored / name
            if not source.exists():
                continue
            current = station.root / name
            if current.exists():
                shutil.move(current, keep / name)
                done.append((current, keep / name))
            shutil.move(source, current)
            done.append((source, current))
            replaced.append(name)
    except OSError as exc:
        problems = _undo(done)
        if not problems:
            with contextlib.suppress(OSError):
                keep.rmdir()
        if problems:
            raise BackupError(
                f"el intercambio ha fallado ({exc}) y no se ha podido deshacer del "
                f"todo: {'; '.join(problems)}. Lo anterior está en {keep}."
            ) from exc
        raise BackupError(
            f"el intercambio ha fallado ({exc}); se ha deshecho y la estación "
            "está como antes."
        ) from exc
    return replaced


def _undo(moves: list[tuple[Path, Path]]) -> list[str]:
    """Deshace movimientos en orden inverso; devuelve los que fallan."""
    problems = []
    for origin, destination in reversed(moves):
        try:
            shutil.move(destination, origin)
        except OSError as exc:
            problems.append(f"{destination} → {origin}: {exc}")
    return problems


def _error_text(message: dict[str, Any]) -> str:
    """Texto de un mensaje ``error`` de ``restic backup --json``."""
    detail = message.get("error", {})
    text = detail.get("message", message) if isinstance(detail, dict) else detail
    item = message.get("item")
    return f"{item}: {text}" if item else str(text)
