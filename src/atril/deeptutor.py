"""Control de DeepTutor a través de su CLI y sus URL de salud.

DeepTutor no es dependencia de atril: se ejecuta el ``deeptutor`` del entorno
virtual de ``app/`` con ``DEEPTUTOR_HOME`` apuntando a la raíz de la estación.
"""

import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass

from atril import net
from atril.config.station import Station
from atril.processes import PortOwner, is_alive, kill_tree, no_window, port_owners


@dataclass(frozen=True, slots=True)
class Orphans:
    """Procesos en los puertos de DeepTutor, separados por pertenencia."""

    own: tuple[PortOwner, ...]
    """De esta estación: se pueden cerrar."""
    foreign: tuple[PortOwner, ...]
    """De otro programa: no se tocan."""


MODEL_CATALOG = "data/user/settings/model_catalog.json"
"""Catálogo de modelos de DeepTutor (con las claves de API), bajo la estación."""


@dataclass(frozen=True, slots=True)
class Assistant:
    """Modelo de chat activo en DeepTutor (sin la clave: solo si la tiene)."""

    provider: str
    """``claude_code``, ``ollama``, ``openai``, ``gemini``..."""
    model: str
    has_key: bool


def active_assistant(station: Station) -> Assistant | None:
    """Modelo de chat activo según el catálogo de DeepTutor.

    Se lee el perfil y el modelo activos de ``services.llm``; la clave puede
    estar en el perfil o en su conexión. Nunca se devuelve la clave.

    Returns:
        El asistente, o ``None`` si no hay catálogo o no se entiende.
    """
    try:
        catalog = json.loads((station.root / MODEL_CATALOG).read_text(encoding="utf-8"))
        llm = catalog["services"]["llm"]
        profile = next(
            p for p in llm["profiles"] if p.get("id") == llm.get("active_profile_id")
        )
        model = next(
            (
                m
                for m in profile.get("models", [])
                if m.get("id") == llm.get("active_model_id")
            ),
            (profile.get("models") or [{}])[0],
        )
        connections = {c.get("id"): c for c in catalog.get("connections", [])}
        reference = profile.get("provider_ref") or {}
        connection = connections.get(reference.get("connection_id"), {})
        has_key = bool(profile.get("api_key") or connection.get("api_key"))
        provider = str(profile.get("binding") or reference.get("binding") or "")
        return Assistant(provider, str(model.get("model") or ""), has_key)
    except (OSError, ValueError, KeyError, TypeError, StopIteration, IndexError):
        return None


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
        """Ejecuta ``deeptutor <args>`` con el entorno de la estación.

        Los subcomandos que lo admiten reciben ``--home`` explícito; ``doctor`` no lo
        acepta y se apoya en ``DEEPTUTOR_HOME``.
        """
        command = [str(self.station.deeptutor_cli), *args]
        return subprocess.run(
            command, env=self.env(), check=False, creationflags=no_window()
        ).returncode

    def _home(self) -> tuple[str, str]:
        """Opción ``--home <raíz>``."""
        return ("--home", str(self.station.root))

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
        return self.run("start", *self._home(), "--detach", "--no-browser")

    def stop(self) -> int:
        """Detiene el lanzador de DeepTutor (puede dejar huérfanos)."""
        return self.run("stop", *self._home())

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

    def launcher_alive(self) -> bool | None:
        """Indica si vive el lanzador de ``launcher.json``.

        Returns:
            ``None`` si no hay estado legible (no se sabe), o si vive su PID.
        """
        try:
            state = json.loads(self.station.launcher_state.read_text(encoding="utf-8"))
            pid = int(state["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return is_alive(pid)

    def launcher_log_tail(self, lines: int = 25) -> list[str]:
        """Últimas líneas del log del lanzador (vacío si no existe)."""
        path = self.station.launcher_log
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.splitlines()[-lines:]
