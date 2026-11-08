"""Bloqueo de la estación para operaciones largas.

La CLI y la GUI comparten la estación: un backup no debe empezar mientras otro
proceso indexa o actualiza DeepTutor. El bloqueo es el fichero
``<estación>/.atril.lock`` con el PID, la hora de inicio de ese proceso y la
operación. Si el proceso ya no existe (o el PID se ha reutilizado), el bloqueo
está abandonado y se sustituye.
"""

import contextlib
import json
import os
import time
from collections.abc import Generator
from pathlib import Path

import psutil

from atril.config.station import Station
from atril.errors import AtrilError

FRESH_SECONDS = 10.0
"""Un bloqueo ilegible más reciente se considera a medio escribir (ocupado)."""

_held: set[Path] = set()
"""Bloqueos de este proceso: una operación puede llamar a otra sin bloquearse."""


class BusyError(AtrilError):
    """La estación está ocupada por otra operación de atril."""


@contextlib.contextmanager
def station_lock(station: Station, operation: str) -> Generator[None]:
    """Reserva la estación mientras dura ``operation``.

    Args:
        station: Estación que se bloquea.
        operation: Nombre de la operación, para el mensaje de ocupado.

    Raises:
        BusyError: Si otro proceso vivo tiene la estación.
    """
    path = station.lock_file
    if path in _held:
        yield
        return
    _acquire(path, operation)
    _held.add(path)
    try:
        yield
    finally:
        _held.discard(path)
        with contextlib.suppress(OSError):
            path.unlink()


def _acquire(path: Path, operation: str) -> None:
    """Crea el fichero de bloqueo; sustituye uno abandonado."""
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            _check_holder(path)
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(_holder(operation), file, ensure_ascii=False)
        return
    raise BusyError(f"no se puede reservar la estación ({path}); vuelve a intentarlo.")


def _holder(operation: str) -> dict[str, object]:
    """Datos de este proceso para el fichero de bloqueo."""
    return {
        "pid": os.getpid(),
        "inicio": psutil.Process().create_time(),
        "operacion": operation,
        "desde": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _check_holder(path: Path) -> None:
    """Lanza :class:`BusyError` si el dueño del bloqueo sigue vivo."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid, started = int(data["pid"]), float(data["inicio"])
    except FileNotFoundError:
        return
    except (OSError, ValueError, KeyError, TypeError):
        if _age(path) < FRESH_SECONDS:
            raise BusyError("la estación está ocupada por otra operación.") from None
        return
    if _alive(pid, started):
        raise BusyError(
            f"la estación está ocupada: {data.get('operacion', '?')} "
            f"(PID {pid}, desde {data.get('desde', '?')}). Espera a que termine."
        )


def _age(path: Path) -> float:
    """Segundos desde la última modificación (infinito si no se puede leer)."""
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return float("inf")


def _alive(pid: int, started: float) -> bool:
    """El proceso existe y es el mismo (no un PID reutilizado)."""
    try:
        return abs(psutil.Process(pid).create_time() - started) < 1.0
    except (psutil.Error, OSError):
        return False
