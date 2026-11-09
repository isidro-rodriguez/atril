import time
from pathlib import Path

import pytest
from support import write, write_other_patches
from typer.testing import CliRunner

from atril import deeptutor as dt_module
from atril import ollama
from atril.commands import deeptutor as commands
from atril.config import load_station
from atril.deeptutor import DeepTutor, Orphans
from atril.main import app
from atril.ollama import OllamaStatus
from atril.patches import PATCHES
from atril.processes import PortOwner

runner = CliRunner()
PATCH = PATCHES["paginas-citas"]


@pytest.fixture
def station(station_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Estación con DeepTutor «instalado», Ollama sano y sin esperas reales."""
    write(load_station(station_dir).deeptutor_cli, "")
    write(station_dir / "app" / PATCH.file, f"x = {{{PATCH.old}}}\n")
    write_other_patches(station_dir / "app", PATCH.name)
    monkeypatch.setattr(
        ollama,
        "get_status",
        lambda url: OllamaStatus(True, "0.12.0", ("qwen3-embedding:8b",)),
    )
    monkeypatch.setattr(ollama, "is_installed", lambda: False)
    clock = [0.0]  # reloj simulado: sleep avanza el tiempo sin esperar

    def fake_sleep(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(time, "sleep", fake_sleep)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(commands.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(DeepTutor, "orphans", lambda self: Orphans((), ()))
    return station_dir


def _invoke(station: Path, *args: str):
    return runner.invoke(app, [*args], env={"ATRIL_ESTACION": str(station)})


def _services(monkeypatch: pytest.MonkeyPatch, backend: bool, frontend: bool) -> None:
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: backend)
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: frontend)


def test_patches_apply_then_check(station: Path) -> None:
    result = _invoke(station, "parches", "--comprobar")
    assert result.exit_code == 0
    assert "pendiente" in result.output

    result = _invoke(station, "parches")
    assert result.exit_code == 0
    assert "aplicado ahora" in result.output
    assert "Reinicia DeepTutor" in result.output

    result = _invoke(station, "parches")
    assert "paginas-citas: aplicado." in result.output
    assert "Reinicia" not in result.output


def test_patches_fail_when_code_changed(station: Path) -> None:
    write(station / "app" / PATCH.file, "codigo nuevo\n")

    result = _invoke(station, "parches")

    assert result.exit_code == 1
    assert "ha cambiado" in result.output


def test_status_stopped(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _services(monkeypatch, backend=False, frontend=False)

    result = _invoke(station, "estado")

    assert result.exit_code == 0, result.output
    assert "Parado." in result.output
    assert "paginas-citas: pendiente" in result.output
    assert "Ollama 0.12.0" in result.output


def test_status_reports_new_atril_version(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.ops import updates

    _services(monkeypatch, backend=False, frontend=False)
    monkeypatch.setattr(
        updates, "check", lambda current="": updates.Release("9.0.0", "https://x")
    )
    monkeypatch.setattr(updates, "installer_folder", lambda prefix=None: None)

    result = _invoke(station, "estado")

    assert result.exit_code == 0, result.output
    assert "Versión nueva de atril: 9.0.0" in result.output
    assert "uv tool upgrade atril" in result.output


def test_status_without_connection_is_not_an_error(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _services(monkeypatch, backend=False, frontend=False)

    result = _invoke(station, "estado")  # net.open_url falla (conftest)

    assert result.exit_code == 0, result.output
    assert "No se ha podido comprobar si hay una versión nueva" in result.output


def test_status_reports_errors(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _services(monkeypatch, backend=True, frontend=False)
    monkeypatch.setattr(ollama, "get_status", lambda url: OllamaStatus(running=False))

    result = _invoke(station, "estado")

    assert result.exit_code == 1
    assert "responde el backend, no el frontend" in result.output
    assert "Ollama no responde" in result.output


def test_status_not_installed(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    load_station(station).deeptutor_cli.unlink()
    _services(monkeypatch, backend=False, frontend=False)

    result = _invoke(station, "estado")

    assert result.exit_code == 1
    assert "No instalado" in result.output


def test_start_when_already_running(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _services(monkeypatch, backend=True, frontend=True)
    monkeypatch.setattr(DeepTutor, "start", lambda self: pytest.fail("no debe lanzar"))

    result = _invoke(station, "arrancar", "--sin-navegador")

    assert result.exit_code == 0
    assert "ya está en marcha" in result.output


def test_start_launches_and_waits(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"started": False}

    def fake_start(self: DeepTutor) -> int:
        state["started"] = True
        return 0

    monkeypatch.setattr(DeepTutor, "start", fake_start)
    monkeypatch.setattr(DeepTutor, "ready", lambda self: state["started"])

    result = _invoke(station, "arrancar", "--sin-navegador")

    assert result.exit_code == 0, result.output
    assert "Listo: http://localhost:3782" in result.output
    # Los parches pendientes se aplican al arrancar (DeepTutor está parado).
    assert "paginas-citas: aplicado ahora" in result.output
    assert PATCH.new in (station / "app" / PATCH.file).read_text(encoding="utf-8")


def test_start_timeout_shows_log(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(load_station(station).launcher_log, "linea 1\nError al compilar\n")
    monkeypatch.setattr(DeepTutor, "start", lambda self: 0)
    monkeypatch.setattr(DeepTutor, "ready", lambda self: False)

    result = _invoke(station, "arrancar", "--espera", "10")

    assert result.exit_code == 1
    assert "Error al compilar" in result.output
    assert "no responde tras 10 s" in result.output


def test_start_refuses_foreign_port(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    foreign = PortOwner(8001, 42, "otro.exe", "C:/otro/otro.exe")
    monkeypatch.setattr(DeepTutor, "ready", lambda self: False)
    monkeypatch.setattr(DeepTutor, "orphans", lambda self: Orphans((), (foreign,)))

    result = _invoke(station, "arrancar")

    assert result.exit_code == 1
    assert "otro.exe (PID 42)" in result.output


def test_stop_kills_own_orphans(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    own = PortOwner(8001, 7, "python.exe", f"{station}/app/.venv/python")
    killed: list[tuple[PortOwner, ...]] = []
    monkeypatch.setattr(DeepTutor, "stop", lambda self: 0)
    monkeypatch.setattr(DeepTutor, "launcher_alive", lambda self: True)
    monkeypatch.setattr(DeepTutor, "orphans", lambda self: Orphans((own,), ()))
    monkeypatch.setattr(DeepTutor, "kill", lambda self, owners: killed.append(owners))
    _services(monkeypatch, backend=False, frontend=False)

    result = _invoke(station, "parar")

    assert result.exit_code == 0, result.output
    assert killed == [(own,)]
    assert "DeepTutor detenido." in result.output


def test_deeptutor_env_and_orphan_split(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # se usa el orphans real, con port_owners simulado
    loaded = load_station(station)
    own = PortOwner(8001, 1, "python", f"{loaded.root}/app/.venv/python")
    foreign = PortOwner(3782, 2, "node", "/otra/ruta/node")
    monkeypatch.setattr(dt_module, "port_owners", lambda ports: [own, foreign])
    dt = DeepTutor(loaded)

    assert dt.orphans() == Orphans((own,), (foreign,))
    assert dt.env()["DEEPTUTOR_HOME"] == str(loaded.root)
    assert dt.health_url == "http://127.0.0.1:8001/health/ready"


def test_start_fails_fast_when_launcher_dies(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = load_station(station)
    write(loaded.launcher_log, "Build failed because of webpack errors\n")
    write(loaded.launcher_state, '{"pid": 999999, "status": "starting"}')
    monkeypatch.setattr(DeepTutor, "start", lambda self: 0)
    monkeypatch.setattr(DeepTutor, "ready", lambda self: False)
    monkeypatch.setattr(dt_module, "is_alive", lambda pid: False)

    result = _invoke(station, "arrancar", "--espera", "600")

    assert result.exit_code == 1
    assert "ha terminado sin arrancar" in result.output
    assert "Build failed" in result.output


def test_launcher_alive(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dt = DeepTutor(load_station(station))
    assert dt.launcher_alive() is None

    write(dt.station.launcher_state, '{"pid": 42}')
    monkeypatch.setattr(dt_module, "is_alive", lambda pid: pid == 42)
    assert dt.launcher_alive() is True


def test_stop_when_already_stopped(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(DeepTutor, "stop", lambda self: pytest.fail("no debe llamarse"))
    monkeypatch.setattr(DeepTutor, "launcher_alive", lambda self: None)
    _services(monkeypatch, backend=False, frontend=False)

    result = _invoke(station, "parar")

    assert result.exit_code == 0, result.output
    assert "No hay lanzador" in result.output
