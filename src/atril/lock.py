"""Bloqueo de la estación para operaciones largas.

La CLI y la GUI comparten la estación: un backup no debe empezar mientras otro
proceso indexa o actualiza DeepTutor. El bloqueo es un bloqueo del sistema
operativo (``msvcrt`` en Windows, ``fcntl`` en el resto) sobre
``<estación>/.atril.lock``: el sistema lo libera si el proceso muere, así que no
hay bloqueos abandonados que limpiar ni carreras al sustituirlos. El fichero
guarda quién lo tiene (PID, operación, hora) para el mensaje de ocupado y no se
borra nunca: borrarlo permitiría a otro proceso bloquear un fichero distinto.
"""

import contextlib
import json
import os
import sys
import time
from collections.abc import Generator
from pathlib import Path

from atril.config.station import Station
from atril.errors import AtrilError

LOCK_OFFSET = 1 << 30
"""Byte que se bloquea en Windows: lejos del texto, que sigue siendo legible."""

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
        BusyError: Si otro proceso tiene la estación.
    """
    path = station.lock_file
    if path in _held:
        yield
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if not try_lock(fd):
            raise BusyError(_busy_message(path))
        _write_holder(fd, operation)
        _held.add(path)
        try:
            yield
        finally:
            _held.discard(path)
            with contextlib.suppress(OSError):
                os.ftruncate(fd, 0)
            unlock(fd)
    finally:
        os.close(fd)


def try_lock(fd: int) -> bool:
    """Intenta el bloqueo exclusivo sin esperar; ``False`` si lo tiene otro."""
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def unlock(fd: int) -> None:
    """Libera el bloqueo de ``fd``."""
    with contextlib.suppress(OSError):
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)


def _write_holder(fd: int, operation: str) -> None:
    """Apunta quién tiene el bloqueo (solo informativo)."""
    holder = {
        "pid": os.getpid(),
        "operacion": operation,
        "desde": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with contextlib.suppress(OSError):
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(holder, ensure_ascii=False).encode("utf-8"))


def _busy_message(path: Path) -> str:
    """Mensaje de ocupado con la operación que tiene la estación, si se sabe."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        detail = f": {data['operacion']} (PID {data['pid']}, desde {data['desde']})"
    except (OSError, ValueError, KeyError, TypeError):
        detail = ""
    return f"la estación está ocupada{detail}. Espera a que termine."
