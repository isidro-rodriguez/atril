"""Control de DeepTutor a través de su CLI y sus URL de salud.

DeepTutor no es dependencia de atril: se ejecuta el ``deeptutor`` del entorno
virtual de ``app/`` con ``DEEPTUTOR_HOME`` apuntando a la raíz de la estación.
"""

import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass

from atril import net
from atril.config.station import Station
from atril.processes import PortOwner, kill_tree, port_owners


@dataclass(frozen=True, slots=True)
class Orphans:
    """Procesos en los puertos de DeepTutor, separados por pertenencia."""

    own: tuple[PortOwner, ...]
    """De esta estación: se pueden cerrar."""
    foreign: tuple[PortOwner, ...]
    """De otro programa: no se tocan."""


class DeepTutor:
    """Instalación de DeepTutor de una estación."""

    def __init__(self, station: Station) -> None:
        """Prepara el control de la instalación de ``station``."""
        self.station = station
        ports = station.deeptutor
        self.health_url = f"http://127.0.0.1:{ports.backend_port}/health/ready"
        self.frontend_url = f"http://localhost:{ports.frontend_port}"

    @property
    def installed(self) -> bool:
        """``True`` si existe el ejecutable ``deeptutor`` del entorno de ``app/``."""
        return self.station.deeptutor_cli.is_file()

    def env(self) -> dict[str, str]:
        """Entorno para el CLI: ``DEEPTUTOR_HOME`` y salida en UTF-8."""
        return {
            **os.environ,
            "DEEPTUTOR_HOME": str(self.station.root),
            "PYTHONUTF8": "1",
        }

    def run(self, *args: str) -> int:
        """Ejecuta ``deeptutor <args> --home <raíz>`` y devuelve el código de salida."""
        command = [
            str(self.station.deeptutor_cli),
            *args,
            "--home",
            str(self.station.root),
        ]
        return subprocess.run(command, env=self.env(), check=False).returncode

    def backend_up(self) -> bool:
        """El backend responde en ``/health/ready``."""
        return net.is_up(self.health_url)

    def frontend_up(self) -> bool:
        """El frontend responde."""
        return net.is_up(self.frontend_url)

    def ready(self) -> bool:
        """Backend y frontend responden."""
        return self.backend_up() and self.frontend_up()

    def start(self) -> int:
        """Lanza DeepTutor en segundo plano, sin abrir el navegador."""
        return self.run("start", "--detach", "--no-browser")

    def stop(self) -> int:
        """Detiene el lanzador de DeepTutor (puede dejar huérfanos)."""
        return self.run("stop")

    def wait(
        self,
        condition: Callable[[], bool],
        timeout: float,
        interval: float = 3.0,
    ) -> bool:
        """Espera a que ``condition`` se cumpla, como mucho ``timeout`` segundos."""
        deadline = time.monotonic() + timeout
        while True:
            if condition():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def orphans(self) -> Orphans:
        """Procesos que escuchan en los puertos de DeepTutor."""
        ports = self.station.deeptutor
        owners = port_owners([ports.backend_port, ports.frontend_port])
        own = tuple(owner for owner in owners if owner.belongs_to(self.station.root))
        foreign = tuple(owner for owner in owners if owner not in own)
        return Orphans(own=own, foreign=foreign)

    def kill(self, owners: tuple[PortOwner, ...]) -> None:
        """Cierra los procesos indicados y sus descendientes."""
        for pid in {owner.pid for owner in owners}:
            kill_tree(pid)

    def launcher_log_tail(self, lines: int = 25) -> list[str]:
        """Últimas líneas del log del lanzador (vacío si no existe)."""
        path = self.station.launcher_log
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.splitlines()[-lines:]
