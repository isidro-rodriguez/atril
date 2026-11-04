import subprocess
import sys
from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import __version__
from atril.main import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"atril {__version__}"


def test_validate_ok(station_dir: Path) -> None:
    result = runner.invoke(app, ["--estacion", str(station_dir), "validar"])

    assert result.exit_code == 0, result.output
    row = next(line for line in result.output.splitlines() if "normativa" in line)
    assert [cell.strip() for cell in row.strip("│ ").split("│")][2:] == ["2", "3"]
    assert "Configuración válida." in result.output


def test_validate_reads_env(station_dir: Path) -> None:
    result = runner.invoke(app, ["validar"], env={"ATRIL_ESTACION": str(station_dir)})

    assert result.exit_code == 0, result.output


def test_validate_error_exits_1(station_dir: Path) -> None:
    write(station_dir / "temarios" / "normativa" / "temario.toml", "[temario]\n")

    result = runner.invoke(app, ["--estacion", str(station_dir), "validar"])

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


def test_first_run_asks_station_and_saves_it(
    station_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.commands import _common

    saved: list[Path] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATRIL_ESTACION", raising=False)
    monkeypatch.setattr(_common, "_interactive", lambda: True)
    monkeypatch.setattr(
        _common, "persist_station", lambda root: saved.append(root) or _common.ok("ok")
    )

    result = CliRunner().invoke(
        app, ["temario", "lista"], input=f"{tmp_path / 'nada'}\n{station_dir}\n"
    )

    assert result.exit_code == 0, result.output
    assert "No hay atril.toml" in result.output
    assert saved == [station_dir.resolve()]
    assert "normativa" in result.output


def test_without_terminal_does_not_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATRIL_ESTACION", raising=False)

    result = CliRunner().invoke(app, ["validar"])

    assert result.exit_code == 1
    assert "ATRIL_ESTACION" in result.output
