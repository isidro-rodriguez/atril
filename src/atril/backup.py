"""Copias de seguridad de la estación en ficheros comprimidos.

Cada copia es un ``.zip`` (deflate 9) o un ``.tar.xz`` (xz 9) con
``atril.toml``, ``data/`` y ``temarios/`` (no ``app/``, que se reconstruye con
``atril instalar``) y un manifiesto ``atril-backup.json`` con la ruta de la
estación. Se escribe en ``.part`` y se renombra al terminar: una copia a medias
nunca pasa por buena.
"""

import contextlib
import io
import json
import shutil
import tarfile
import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from atril import __version__
from atril.checks import Finding, info, ok, warning
from atril.config.station import Station

MANIFEST = "atril-backup.json"
"""Manifiesto dentro de cada copia: ruta de la estación, fecha y versión."""

PREFIX = "atril-"
"""Prefijo de las copias; la retención solo toca ficheros ``atril-*``."""

EXTENSIONS = {"zip": ".zip", "tar.xz": ".tar.xz"}
"""Extensión de cada formato."""

EXCLUDED_DIRS = ("data/atril/logs", "data/atril/bundles")
"""Carpetas que no se copian: logs y los bundles de git de versiones antiguas."""

EXCLUDED_SUFFIXES = (".part", ".nuevo")
"""Descargas a medias."""

SECRET_FILES = ("data/user/settings/model_catalog.json",)
"""Ficheros de DeepTutor con claves de API en claro: se copian con las claves vacías."""

SECRET_HINTS = ("api_key", "apikey", "token", "secret", "password")
"""Campos que DeepTutor trata como secretos (los mismos que oculta en su web)."""

STALE_DAYS = 7
"""Días a partir de los que la última copia se considera antigua."""

LOW_SPACE = 10 * 1024**3
"""Espacio libre por debajo del que se avisa (las KB ocupan varios GB)."""

Progress = Callable[[int], None]
"""Recibe los bytes leídos desde la última llamada."""


class BackupError(Exception):
    """Error de backup o restauración, con mensaje en español."""


@dataclass(frozen=True, slots=True)
class Archive:
    """Copia de seguridad encontrada en un destino."""

    path: Path
    size: int

    @property
    def stamp(self) -> str:
        """Fecha de la copia (``AAAAMMDD-HHMMSS``), sacada del nombre."""
        name = self.path.name.removeprefix(PREFIX)
        return name.split(".", 1)[0]


@dataclass(slots=True)
class Result:
    """Resultado de crear una copia."""

    archive: Path
    files: int = 0
    read_bytes: int = 0
    unread: list[str] = field(default_factory=list)
    """Ficheros que no se pudieron leer: la copia queda incompleta."""
    redacted: int = 0
    """Claves de API vaciadas en la copia."""

    @property
    def incomplete(self) -> bool:
        """``True`` si faltan ficheros en la copia."""
        return bool(self.unread)


def is_reachable(folder: Path) -> bool:
    """El destino existe o puede crearse (su carpeta padre existe).

    Si falta también la carpeta padre, es un disco desconectado.
    """
    return folder.is_dir() or folder.parent.is_dir()


def station_files(station: Station) -> Iterator[tuple[Path, str]]:
    """Ficheros que se copian, con su nombre dentro de la copia (``data/...``)."""
    root = station.root
    if (root / "atril.toml").is_file():
        yield root / "atril.toml", "atril.toml"
    for top in ("data", "temarios"):
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            name = path.relative_to(root).as_posix()
            if not path.is_file() or path.name.endswith(EXCLUDED_SUFFIXES):
                continue
            if any(name.startswith(f"{folder}/") for folder in EXCLUDED_DIRS):
                continue
            yield path, name


def archive_name(archive_format: str, stamp: str | None = None) -> str:
    """Nombre de una copia nueva: ``atril-AAAAMMDD-HHMMSS.zip``."""
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    return f"{PREFIX}{stamp}{EXTENSIONS[archive_format]}"


def create(station: Station, folder: Path, progress: Progress | None = None) -> Result:
    """Crea una copia de la estación en ``folder``.

    Raises:
        BackupError: Si no se puede escribir la copia.
    """
    archive_format = station.backup.archive_format
    target = folder / archive_name(archive_format)
    partial = target.with_name(target.name + ".part")
    result = Result(target)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with _open(partial, archive_format) as archive:
            for path, name in station_files(station):
                try:
                    if name in SECRET_FILES:
                        data, count = redact_secrets(path.read_bytes())
                        _put_bytes(archive, name, data)
                        result.redacted += count
                    else:
                        _put_file(archive, path, name)
                    size = path.stat().st_size
                except OSError as exc:
                    result.unread.append(f"{name}: {exc}")
                    continue
                result.files += 1
                result.read_bytes += size
                if progress:
                    progress(size)
            _put_bytes(archive, MANIFEST, _manifest(station, result))
        partial.replace(target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            partial.unlink()
        raise BackupError(f"no se puede escribir la copia en {folder}: {exc}") from exc
    return result


def _manifest(station: Station, result: Result) -> bytes:
    """Manifiesto de la copia: origen, fecha, versión y claves vaciadas."""
    data = {
        "estacion": str(station.root),
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "atril": __version__,
        "claves_vaciadas": result.redacted,
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def redact_secrets(raw: bytes) -> tuple[bytes, int]:
    """Vacía las claves de un JSON de DeepTutor; devuelve el JSON y cuántas eran.

    Solo se vacían textos no vacíos (``max_tokens`` es un número y se respeta).
    Si no es JSON válido se deja tal cual: DeepTutor lo rechazaría igualmente.

    Examples:
        >>> data, count = redact_secrets(b'{"llm": {"api_key": "sk", "max_tokens": 9}}')
        >>> count, json.loads(data)
        (1, {'llm': {'api_key': '', 'max_tokens': 9}})
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return raw, 0
    count = 0

    def clean(value: Any, secret: bool) -> Any:
        nonlocal count
        if isinstance(value, dict):
            return {
                key: clean(item, secret or _is_secret(key))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item, secret) for item in value]
        if secret and isinstance(value, str) and value:
            count += 1
            return ""
        return value

    cleaned = clean(data, False)
    text = json.dumps(cleaned, ensure_ascii=False, indent=2)
    return text.encode("utf-8"), count


def _is_secret(key: str) -> bool:
    """Campo con credenciales (o cabeceras, que suelen llevarlas)."""
    lowered = key.lower()
    return lowered == "extra_headers" or any(hint in lowered for hint in SECRET_HINTS)


def _open(path: Path, archive_format: str) -> zipfile.ZipFile | tarfile.TarFile:
    """Abre una copia nueva con la compresión máxima del formato."""
    if archive_format == "zip":
        return zipfile.ZipFile(
            path, "w", zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True
        )
    return tarfile.open(path, "w:xz", preset=9)


def _put_bytes(
    archive: zipfile.ZipFile | tarfile.TarFile, name: str, data: bytes
) -> None:
    """Añade un fichero en memoria (el manifiesto)."""
    if isinstance(archive, zipfile.ZipFile):
        archive.writestr(name, data)
        return
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(time.time())
    archive.addfile(info, io.BytesIO(data))


def _put_file(
    archive: zipfile.ZipFile | tarfile.TarFile, path: Path, name: str
) -> None:
    """Añade un fichero del disco."""
    if isinstance(archive, zipfile.ZipFile):
        archive.write(path, name)
    else:
        archive.add(path, name, recursive=False)


def verify(path: Path) -> dict[str, str]:
    """Lee la copia entera (CRC del zip o flujo del xz) y devuelve su manifiesto.

    Raises:
        BackupError: Si está dañada o no es una copia de atril.
    """
    try:
        if path.name.endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                broken = archive.testzip()
                if broken is not None:
                    raise BackupError(f"{path.name}: {broken} está dañado.")
                manifest = archive.read(MANIFEST)
                names = archive.namelist()
        else:
            manifest = b""
            names = []
            with tarfile.open(path, "r:xz") as archive:
                for member in archive:
                    names.append(member.name)
                    reader = archive.extractfile(member)
                    if reader is None:
                        continue
                    if member.name == MANIFEST:
                        manifest = reader.read()
                    # Leer hasta el final comprueba el flujo xz sin cargarlo entero.
                    while reader.read(1 << 20):
                        pass
        _check_contents(path, names)
        return json.loads(manifest)
    except BackupError:
        raise
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise BackupError(f"{path.name}: copia dañada o incompleta ({exc}).") from exc


def _check_contents(path: Path, names: list[str]) -> None:
    """Exige ``atril.toml``, ``data/`` y ``temarios/`` en la copia."""
    missing = [
        item
        for item, present in (
            ("atril.toml", "atril.toml" in names),
            ("data/", any(name.startswith("data/") for name in names)),
            ("temarios/", any(name.startswith("temarios/") for name in names)),
        )
        if not present
    ]
    if missing:
        raise BackupError(f"{path.name}: le falta {', '.join(missing)}.")


def age_days(archive: Archive, now: float | None = None) -> float:
    """Días desde que se hizo la copia (según su nombre)."""
    made = time.mktime(time.strptime(archive.stamp, "%Y%m%d-%H%M%S"))
    return ((now or time.time()) - made) / 86400


def station_findings(station: Station) -> list[Finding]:
    """Espacio libre, última copia y restauraciones a medias (para ``atril estado``)."""
    findings = [_free_space(station.root, "Estación")]
    latest: Archive | None = None
    for folder in station.backup.destinations:
        if not is_reachable(folder):
            findings.append(info(f"{folder}: no conectado."))
            continue
        findings.append(
            _free_space(folder if folder.is_dir() else folder.parent, str(folder))
        )
        found = archives(folder)
        if found and (latest is None or found[-1].stamp > latest.stamp):
            latest = found[-1]
    findings.append(latest_finding(latest))
    root = station.root
    findings += [
        warning(f"{leftover}: restauración interrumpida; revísala y bórrala.")
        for leftover in sorted(root.parent.glob(f"{root.name}.restaurar-*"))
    ]
    findings += [
        info(f"{kept}: estado anterior a una restauración; bórralo si sobra.")
        for kept in sorted(root.parent.glob(f"{root.name}.previo-*"))
    ]
    return findings


def latest_finding(latest: Archive | None) -> Finding:
    """Antigüedad de la última copia: aviso si no hay o si tiene más de una semana."""
    if latest is None:
        return warning("No hay ninguna copia de seguridad: ejecuta atril backup.")
    days = age_days(latest)
    text = f"Última copia: {latest.path.name} (hace {days:.0f} días)."
    return warning(text) if days > STALE_DAYS else ok(text)


def _free_space(folder: Path, label: str) -> Finding:
    """Espacio libre en el disco de ``folder``; aviso si queda poco."""
    try:
        free = shutil.disk_usage(folder).free
    except OSError as exc:
        return warning(f"{label}: no se puede consultar el espacio libre ({exc}).")
    text = f"{label}: {free / 1024**3:.1f} GiB libres."
    return warning(text) if free < LOW_SPACE else ok(text)


def archives(folder: Path) -> list[Archive]:
    """Copias de atril en ``folder``, de la más antigua a la más reciente."""
    if not folder.is_dir():
        return []
    found = [
        Archive(path, path.stat().st_size)
        for path in folder.iterdir()
        if path.is_file()
        and path.name.startswith(PREFIX)
        and path.name.endswith(tuple(EXTENSIONS.values()))
    ]
    return sorted(found, key=lambda archive: archive.stamp)


def prune(folder: Path, keep: int) -> list[Path]:
    """Borra las copias más antiguas y deja las ``keep`` más recientes."""
    removed = []
    for archive in archives(folder)[:-keep]:
        archive.path.unlink()
        removed.append(archive.path)
    return removed


def extract(archive: Path, target: Path) -> dict[str, str]:
    """Extrae una copia en ``target`` (vacía) y devuelve su manifiesto.

    Rechaza rutas absolutas o con ``..``: una copia nunca escribe fuera.

    Raises:
        BackupError: Si la copia está dañada o tiene rutas peligrosas.
    """
    try:
        target.mkdir(parents=True, exist_ok=False)
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as source:
                for name in source.namelist():
                    _check_name(name)
                source.extractall(target)
        else:
            with tarfile.open(archive, "r:xz") as source:
                source.extractall(target, filter="data")
        manifest = target / MANIFEST
        data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest.unlink()
    except BackupError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise BackupError(f"{archive.name}: no se puede extraer ({exc}).") from exc
    return data


def _check_name(name: str) -> None:
    """Rechaza nombres de zip absolutos o que salen de la carpeta."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise BackupError(f"la copia tiene una ruta no permitida: {name!r}.")


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
    if not (restored / "atril.toml").is_file():
        raise BackupError(f"{restored} no contiene atril.toml: no es una estación.")
    try:
        keep.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise BackupError(f"no se puede preparar {keep}: {exc}") from exc
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
