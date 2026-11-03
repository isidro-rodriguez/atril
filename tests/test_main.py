import subprocess
import sys
from pathlib import Path

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
