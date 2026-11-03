from pathlib import Path

import pytest
from test_sources import PDF_V1, PDF_V2, FakeWeb
from typer.testing import CliRunner

from atril import sources
from atril.main import app

runner = CliRunner()
CTE_URL = "https://www.codigotecnico.org/pdf/Documentos/SI/DBSI.pdf"
LOE_URL = "https://www.boe.es/buscar/pdf/1999/BOE-A-1999-21567-consolidado.pdf"


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> FakeWeb:
    fake = FakeWeb()
    fake.pages[CTE_URL] = PDF_V1
    fake.pages[LOE_URL] = PDF_V1
    monkeypatch.setattr(sources.net, "open_url", fake.open_url)
    return fake


def _invoke(station: Path, *args: str):
    return runner.invoke(app, ["--estacion", str(station), *args])


def test_download_then_list_and_coverage(station_dir: Path, web: FakeWeb) -> None:
    result = _invoke(station_dir, "fuentes", "descargar", "normativa")

    assert result.exit_code == 0, result.output
    assert result.output.count("descargada") == 2
    assert "manual" in result.output

    listing = _invoke(station_dir, "temario", "lista")
    row = next(line for line in listing.output.splitlines() if "normativa" in line)
    assert [cell.strip() for cell in row.strip("│ ").split("│")][2:] == [
        "2",
        "3",
        "2",
        "1",
    ]

    coverage = _invoke(station_dir, "temario", "cobertura", "normativa")
    assert "norm-edificacion-cte" in coverage.output
    assert "presente" in coverage.output


def test_download_failure_exits_1(station_dir: Path, web: FakeWeb) -> None:
    del web.pages[LOE_URL]

    result = _invoke(station_dir, "fuentes", "descargar", "normativa", "loe")

    assert result.exit_code == 1
    assert "404" in result.output


def test_check_respects_frequency(
    station_dir: Path, web: FakeWeb, monkeypatch: pytest.MonkeyPatch
) -> None:
    _invoke(station_dir, "fuentes", "descargar", "normativa")
    web.requests.clear()

    result = _invoke(station_dir, "fuentes", "comprobar", "normativa")
    assert "no tocan todavía" in result.output
    assert web.requests == []

    web.pages[CTE_URL] = PDF_V2
    result = _invoke(station_dir, "fuentes", "comprobar", "normativa", "--todas")

    assert result.exit_code == 0, result.output
    assert "actualizada" in result.output
    assert "Reindexa esas KB" in result.output
    assert "norm-edificacion-cte" in result.output


def test_unknown_syllabus_and_source(station_dir: Path) -> None:
    result = _invoke(station_dir, "temario", "cobertura", "otro")
    assert result.exit_code == 1
    assert "disponibles: normativa" in result.output

    result = _invoke(station_dir, "fuentes", "descargar", "normativa", "nada")
    assert result.exit_code == 1
    assert "fuentes desconocidas" in result.output
