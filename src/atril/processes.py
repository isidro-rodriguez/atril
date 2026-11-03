"""Procesos que escuchan en los puertos de DeepTutor (huérfanos incluidos).

``deeptutor stop`` solo detiene el lanzador; si el backend o el frontend quedan
vivos, siguen ocupando los puertos. Aquí se identifican y se cierran, pero solo
si su línea de comandos pertenece a la estación.
"""

import contextlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True, slots=True)
class PortOwner:
    """Proceso que escucha en un puerto."""

    port: int
    pid: int
    name: str
    cmdline: str
    args: tuple[str, ...] = ()
    """Argumentos tal cual (si no se conocen, se parte ``cmdline`` por espacios)."""

    def belongs_to(self, root: Path) -> bool:
        r"""Indica si algún argumento es una ruta dentro de ``root``.

        Se comparan rutas, no texto: ``D:\DeepTutorBackup`` no está dentro de
        ``D:\DeepTutor``. Sin distinguir mayúsculas ni separadores (Windows).

        Examples:
            >>> owner = PortOwner(8001, 1, "python", r"D:\DT\app\python.exe")
            >>> owner.belongs_to(Path("D:/DT")), owner.belongs_to(Path("D:/D"))
            (True, False)
        """
        base = _normalize(str(root))
        arguments = self.args or tuple(self.cmdline.split())
        for argument in arguments:
            for candidate in (argument, *argument.split("=")[1:]):
                path = _normalize(candidate)
                if path == base or path.startswith(base + "/"):
                    return True
        return False


def _normalize(path: str) -> str:
    r"""Ruta comparable: sin comillas, con ``/``, sin ``/`` final y en minúsculas.

    Examples:
        >>> _normalize(r'"D:\Desarrollo\DeepTutor\"')
        'd:/desarrollo/deeptutor'
    """
    text = path.strip().strip('"').strip("'").replace("\\", "/")
    while "//" in text[1:]:
        text = text[0] + text[1:].replace("//", "/")
    return text.rstrip("/").casefold()


def lower_priority(pid: int) -> bool:
    """Baja la prioridad de CPU y de disco de un proceso (sus hijos la heredan).

    No cambia lo que hace el proceso, solo cede el turno a las aplicaciones
    interactivas: el equipo responde mientras se indexa.

    Returns:
        ``True`` si se ha podido bajar la prioridad de CPU.
    """
    try:
        process = psutil.Process(pid)
        windows = hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS")
        process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if windows else 10)
    except (psutil.Error, OSError):
        return False
    with contextlib.suppress(psutil.Error, OSError, AttributeError, ValueError):
        if hasattr(psutil, "IOPRIO_LOW"):
            process.ionice(psutil.IOPRIO_LOW)
        elif hasattr(psutil, "IOPRIO_CLASS_BE"):
            process.ionice(psutil.IOPRIO_CLASS_BE, value=7)
    return True


def port_owners(ports: Iterable[int]) -> list[PortOwner]:
    """Procesos que escuchan en ``ports``, ordenados por puerto y PID."""
    wanted = set(ports)
    found: dict[tuple[int, int], PortOwner] = {}
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN or not conn.laddr or conn.pid is None:
            continue
        port = conn.laddr.port
        if port in wanted and (port, conn.pid) not in found:
            found[(port, conn.pid)] = _describe(port, conn.pid)
    return [found[key] for key in sorted(found)]


def _describe(port: int, pid: int) -> PortOwner:
    """Nombre y línea de comandos de ``pid`` (vacíos si no se pueden leer)."""
    try:
        process = psutil.Process(pid)
        args = tuple(process.cmdline())
        return PortOwner(port, pid, process.name(), " ".join(args), args)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return PortOwner(port, pid, "", "")


def is_alive(pid: int) -> bool:
    """Indica si existe un proceso con ese PID."""
    return psutil.pid_exists(pid)


def kill_tree(pid: int) -> None:
    """Cierra ``pid`` y todos sus descendientes; ignora los que ya no existen."""
    try:
        parent = psutil.Process(pid)
        processes = [*parent.children(recursive=True), parent]
    except psutil.NoSuchProcess:
        return
    for process in processes:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            continue
    psutil.wait_procs(processes, timeout=5)
