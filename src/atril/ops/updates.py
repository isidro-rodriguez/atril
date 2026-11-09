"""Versiones nuevas de atril: la última release de GitHub y su instalador.

La ventana pregunta al abrirse (si ``[atril] buscar_actualizaciones`` lo permite)
y, en una instalación hecha con el instalador de Windows, descarga el nuevo y lo
lanza en modo silencioso: cierra atril, instala y vuelve a abrir la ventana.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from atril import __version__, net, processes
from atril.checks import Finding, info, ok, warning
from atril.errors import AtrilError, CancelledError
from atril.ops import Reporter

LATEST_URL = "https://api.github.com/repos/isidro-rodriguez/atril/releases/latest"
"""Última release publicada (API de GitHub, sin autenticación)."""

INSTALLER_SUFFIX = "-setup.exe"
"""Final del nombre del instalador entre los ficheros de la release."""

_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True, slots=True)
class Release:
    """Una versión publicada de atril."""

    version: str
    page: str
    """Página de la release (novedades)."""
    installer_url: str | None = None
    installer_sha256: str | None = None


def parse_version(text: str) -> tuple[int, int, int] | None:
    """``X.Y.Z`` (con o sin ``v``) como tupla; ``None`` si no lo es.

    Examples:
        >>> parse_version("v0.30.0")
        (0, 30, 0)
        >>> parse_version("1.0.0rc1") is None
        True
    """
    found = _VERSION.fullmatch(text.strip())
    if found is None:
        return None
    major, minor, patch = (int(part) for part in found.groups())
    return major, minor, patch


def is_newer(candidate: str, current: str) -> bool:
    """``candidate`` es posterior a ``current`` (las no reconocibles, nunca).

    Examples:
        >>> is_newer("0.31.0", "0.30.2")
        True
        >>> is_newer("0.30.0", "0.30.0")
        False
    """
    new, old = parse_version(candidate), parse_version(current)
    return new is not None and old is not None and new > old


def latest_release(timeout: float = 10.0) -> Release:
    """Última release publicada en GitHub.

    Raises:
        AtrilError: Si no hay conexión o la respuesta no se entiende.
    """
    try:
        with net.open_url(LATEST_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        version = str(data["tag_name"]).removeprefix("v")
        page = str(data["html_url"])
        assets = list(data.get("assets") or [])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AtrilError(f"no se ha podido consultar la última versión: {exc}") from exc
    installer = next(
        (a for a in assets if str(a.get("name", "")).endswith(INSTALLER_SUFFIX)), None
    )
    if installer is None:
        return Release(version, page)
    digest = str(installer.get("digest") or "")
    return Release(
        version,
        page,
        installer_url=str(installer.get("browser_download_url") or "") or None,
        installer_sha256=digest.removeprefix("sha256:") or None,
    )


def check(current: str = __version__) -> Release | None:
    """La última release si es posterior a ``current``; si no, ``None``.

    Raises:
        AtrilError: Si no se ha podido consultar.
    """
    release = latest_release()
    return release if is_newer(release.version, current) else None


def update_findings(current: str = __version__) -> list[Finding]:
    """Si hay una versión nueva de atril, para ``atril estado``.

    Sin conexión no es un error: solo se dice que no se ha podido comprobar.
    """
    try:
        release = check(current)
    except AtrilError:
        return [info("No se ha podido comprobar si hay una versión nueva de atril.")]
    if release is None:
        return [ok(f"atril {current}: es la última versión.")]
    return [
        warning(f"Versión nueva de atril: {release.version} (tienes la {current}).")
    ]


def installer_folder(prefix: Path | None = None) -> Path | None:
    """Carpeta del instalador de Windows si atril se instaló con él.

    El instalador deja ``uv.exe`` y ``unins000.exe`` en su carpeta, y atril vive
    en ``herramientas/atril`` dentro de ella. Solo en Windows.
    """
    if sys.platform != "win32" and prefix is None:
        return None
    start = Path(sys.prefix if prefix is None else prefix).resolve()
    for folder in start.parents:
        if (folder / "unins000.exe").is_file() and (folder / "uv.exe").is_file():
            return folder
    return None


def download_installer(
    release: Release,
    reporter: Reporter,
    cancel: threading.Event | None = None,
    folder: Path | None = None,
) -> Path:
    """Descarga el instalador de ``release`` y comprueba su SHA-256.

    Se escribe como ``.part`` y solo se renombra si la suma coincide.

    Raises:
        AtrilError: Si la release no trae instalador, falla la descarga o la suma
            no coincide.
        CancelledError: Si se cancela.
    """
    if release.installer_url is None or release.installer_sha256 is None:
        raise AtrilError(f"la versión {release.version} aún no tiene instalador.")
    target_dir = folder or Path(tempfile.gettempdir()) / "atril-actualizacion"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"atril-{release.version}{INSTALLER_SUFFIX}"
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    try:
        with (
            reporter.busy(f"Descargando atril {release.version}...") as update,
            net.open_url(release.installer_url) as response,
            part.open("wb") as out,
        ):
            done = 0
            while chunk := response.read(1 << 20):
                if cancel is not None and cancel.is_set():
                    raise CancelledError("descarga cancelada.")
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                update(f"Descargando atril {release.version} ({done >> 20} MB)...")
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise AtrilError(f"no se ha podido descargar el instalador: {exc}") from exc
    except CancelledError:
        part.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != release.installer_sha256.lower():
        part.unlink(missing_ok=True)
        raise AtrilError("el instalador descargado no coincide con el publicado.")
    part.replace(target)
    return target


def launch_installer(installer: Path) -> None:
    """Lanza el instalador sin preguntas y con reapertura de la ventana al final.

    Quien lo llama debe cerrarse en seguida: el instalador espera a que este
    proceso termine (``/esperar``) antes de sustituir sus ficheros.
    """
    subprocess.Popen(
        [
            str(installer),
            "/SILENT",
            "/SP-",
            "/NOCANCEL",
            "/abrir=si",
            f"/esperar={os.getpid()}",  # no toca el entorno hasta que esto termine
        ],
        creationflags=processes.no_window(),
        close_fds=True,
    )
