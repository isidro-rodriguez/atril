from pathlib import Path

import pytest
from support import write, write_other_patches
from typer.testing import CliRunner

from atril.checks import error, info, ok
from atril.commands import install as commands
from atril.config import load_station
from atril.deeptutor import DeepTutor
from atril.install import Installer, StepError
from atril.main import app
from atril.patches import PATCHES

runner = CliRunner()
PATCH = PATCHES["paginas-citas"]


@pytest.fixture
def station(station_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Estación con DeepTutor parado y todos los pasos del instalador simulados."""
    loaded = load_station(station_dir)
    write(loaded.deeptutor_cli, "")
    (loaded.app_dir / ".git").mkdir()
    write(loaded.app_dir / PATCH.file, f"x = {{{PATCH.new}}}\n")
    write_other_patches(loaded.app_dir, PATCH.name)
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: False)
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: False)
    monkeypatch.setattr(commands.install, "check_tools", lambda: [ok("git")])
    for step in ("clone", "frontend", "embedding_model"):
        monkeypatch.setattr(Installer, step, lambda self, s=step, **kw: ok(s))
    for step in ("configure", "runtime_settings", "doctor"):
        monkeypatch.setattr(Installer, step, lambda self, s=step: [ok(s)])
    monkeypatch.setattr(Installer, "python_env", lambda self, docling: [ok("python")])
    monkeypatch.setattr(Installer, "venv_matches", lambda self: True)
    return station_dir


def _invoke(station: Path, *args: str):
    return runner.invoke(app, [*args], env={"ATRIL_ESTACION": str(station)})


def test_install_happy_path(station: Path) -> None:
    result = _invoke(station, "instalar")

    assert result.exit_code == 0, result.output
    assert "paginas-citas: aplicado." in result.output
    assert "DeepTutor instalado" in result.output


def test_install_refuses_when_running(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: True)

    result = _invoke(station, "instalar")

    assert result.exit_code == 1
    assert "atril parar" in result.output


def test_install_stops_on_step_error(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: Installer, docling: bool) -> list:
        raise StepError("requirements/full.txt ha fallado (código 1).")

    monkeypatch.setattr(Installer, "python_env", broken)

    result = _invoke(station, "instalar")

    assert result.exit_code == 1
    assert "requirements/full.txt ha fallado" in result.output
    assert "DeepTutor instalado" not in result.output


def test_update_same_version(station: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        Installer, "update_checkout", lambda self, commit=None: ("a1 x", "a1 x")
    )
    monkeypatch.setattr(
        Installer, "python_env", lambda self, docling: pytest.fail("no debe reinstalar")
    )

    result = _invoke(station, "actualizar")

    assert result.exit_code == 0, result.output
    assert "paginas-citas: deshecho." in result.output
    assert "Sin cambios" in result.output
    assert "paginas-citas: aplicado." in result.output
    assert "runtime_settings" in result.output and "doctor" in result.output
    assert PATCH.new in (load_station(station).app_dir / PATCH.file).read_text()


def test_update_recreates_venv_with_other_python(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Installer, "update_checkout", lambda self, commit=None: ("a1 x", "a1 x")
    )
    monkeypatch.setattr(Installer, "venv_matches", lambda self: False)

    result = _invoke(station, "actualizar")

    assert result.exit_code == 0, result.output
    assert "python" in result.output


def test_update_fails_on_doctor_error(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Installer, "update_checkout", lambda self, commit=None: ("a1 x", "a1 x")
    )
    monkeypatch.setattr(Installer, "doctor", lambda self: [error("LLM: sin clave")])

    result = _invoke(station, "actualizar")

    assert result.exit_code == 1
    assert "LLM: sin clave" in result.output


def test_update_new_version_restarts(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: True)
    monkeypatch.setattr(commands, "shutdown", lambda dt: calls.append("parar"))
    monkeypatch.setattr(
        commands, "launch", lambda dt, timeout: calls.append("arrancar")
    )
    monkeypatch.setattr(
        Installer, "update_checkout", lambda self, commit=None: ("a1 x", "b2 y")
    )
    hashes = iter(["lock-1", "lock-2"])
    monkeypatch.setattr(Installer, "frontend_lock_hash", lambda self: next(hashes))
    forced: list[bool] = []
    monkeypatch.setattr(
        Installer,
        "frontend",
        lambda self, force=False: forced.append(force) or info(""),
    )

    result = _invoke(station, "actualizar")

    assert result.exit_code == 0, result.output
    assert "a1 x → b2 y" in result.output
    assert forced == [True]
    assert calls == ["parar", "arrancar"]


def test_update_fails_when_patch_no_longer_fits(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_file = load_station(station).app_dir / PATCH.file

    def new_code(self: Installer, commit: str | None = None) -> tuple[str, str]:
        app_file.write_text("codigo reescrito\n")
        return ("a1 x", "b2 y")

    monkeypatch.setattr(Installer, "update_checkout", new_code)
    monkeypatch.setattr(Installer, "frontend_lock_hash", lambda self: "igual")

    result = _invoke(station, "actualizar")

    assert result.exit_code == 1
    assert "ha cambiado" in result.output


def test_update_to_commit_shows_how_to_go_back(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str | None] = []
    old = "a" * 40

    def checkout(self: Installer, commit: str | None = None) -> tuple[str, str]:
        calls.append(commit)
        return (f"{old} viejo", f"{'b' * 40} nuevo")

    monkeypatch.setattr(Installer, "update_checkout", checkout)
    monkeypatch.setattr(Installer, "frontend_lock_hash", lambda self: "igual")

    result = _invoke(station, "actualizar", "--commit", "c" * 40)

    assert result.exit_code == 0, result.output
    assert calls == ["c" * 40]
    assert f"atril actualizar --commit {old}" in result.output
