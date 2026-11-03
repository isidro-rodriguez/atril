"""Procesos que escuchan en los puertos de DeepTutor (huérfanos incluidos).

``deeptutor stop`` solo detiene el lanzador; si el backend o el frontend quedan
vivos, siguen ocupando los puertos. Aquí se identifican y se cierran, pero solo
si su línea de comandos pertenece a la estación.
"""

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

    def belongs_to(self, root: Path) -> bool:
        r"""Indica si la línea de comandos contiene ``root`` (sin mayúsculas).

        Examples:
            >>> owner = PortOwner(8001, 1, "python.exe", r"D:\DT\app\.venv\python.exe")
            >>> owner.belongs_to(Path("D:/DT")), owner.belongs_to(Path("D:/Otro"))
            (True, False)
        """
        cmdline = self.cmdline.replace("\\", "/").casefold()
        return root.as_posix().casefold() in cmdline


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
        return PortOwner(port, pid, process.name(), " ".join(process.cmdline()))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return PortOwner(port, pid, "", "")


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
