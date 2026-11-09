import subprocess
import sys
from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import __version__
from atril.checks import ok
from atril.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"atril {__version__}"


def test_validate_ok(station_dir: Path) -> None:
    result = runner.invoke(app, ["validar"], env={"ATRIL_ESTACION": str(station_dir)})

    assert result.exit_code == 0, result.output
    row = next(line for line in result.output.splitlines() if "normativa" in line)
    assert [cell.strip() for cell in row.strip("│ ").split("│")][2:] == ["2", "3"]
    assert "Configuración válida." in result.output


def test_validate_reads_env(station_dir: Path) -> None:
    result = runner.invoke(app, ["validar"], env={"ATRIL_ESTACION": str(station_dir)})

    assert result.exit_code == 0, result.output


def test_validate_error_exits_1(station_dir: Path) -> None:
    write(station_dir / "temarios" / "normativa" / "temario.toml", "[temario]\n")

    result = runner.invoke(app, ["validar"], env={"ATRIL_ESTACION": str(station_dir)})

    assert result.exit_code == 1
    assert "falta la clave obligatoria 'nombre'" in result.output


def test_module_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atril", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "validar" in result.stdout


@pytest.fixture
def first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Sin estación guardada, con terminal y sin escribir en el entorno real."""
    from atril.commands import _common

    saved: list[Path] = []
    monkeypatch.delenv("ATRIL_ESTACION", raising=False)
    monkeypatch.setattr(_common, "saved_station", lambda: None)
    monkeypatch.setattr(_common, "_interactive", lambda: True)
    monkeypatch.setattr(
        _common, "persist_station", lambda root: saved.append(root) or ok("")
    )
    return saved


def test_first_run_offers_current_folder(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch, first_run: list[Path]
) -> None:
    monkeypatch.chdir(station_dir)

    result = CliRunner().invoke(app, ["temario", "lista"], input="s\n")

    assert result.exit_code == 0, result.output
    assert first_run == [station_dir]
    assert "normativa" in result.output


def test_first_run_asks_location(
    station_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_run: list[Path],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["temario", "lista"], input=f"{station_dir}\ns\n")

    assert result.exit_code == 0, result.output
    assert first_run == [station_dir.resolve()]


def test_first_run_initializes_new_station(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first_run: list[Path]
) -> None:
    monkeypatch.chdir(tmp_path)
    new = tmp_path / "estacion-nueva"

    result = CliRunner().invoke(app, ["validar"], input=f"{new}\ns\n")

    assert result.exit_code == 0, result.output
    assert (new / "atril.toml").is_file()
    assert first_run == [new.resolve()]


def test_without_terminal_does_not_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.commands import _common

    monkeypatch.delenv("ATRIL_ESTACION", raising=False)
    monkeypatch.setattr(_common, "saved_station", lambda: None)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["validar"])

    assert result.exit_code == 1
    assert "ATRIL_ESTACION" in result.output


def test_gui_opens_window_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    from atril.commands import gui

    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(
        gui.subprocess, "Popen", lambda args, **kw: calls.append((args, kw))
    )

    result = runner.invoke(app, ["gui"])

    assert result.exit_code == 0, result.output
    assert "Ventana de atril abierta." in result.output
    [(args, options)] = calls
    assert args[1:] == ["-c", "from atril.gui import main; main()"]
    assert options["stdin"] is subprocess.DEVNULL
    if sys.platform == "win32":
        assert options["creationflags"] & 0x8  # DETACHED_PROCESS
        assert Path(args[0]).name.lower() in {"pythonw.exe", "python.exe"}
    else:
        assert options["start_new_session"]
        assert options["creationflags"] == 0
