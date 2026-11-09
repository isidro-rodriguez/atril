"""Fixtures comunes de las pruebas."""

import shutil
from pathlib import Path

import pytest
from support import EXAMPLES


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin red: cada prueba que descarga sustituye ``net.open_url`` por su cuenta."""
    from atril import net

    def offline(url: str, timeout: float = 300.0) -> None:
        raise OSError(f"sin red en las pruebas: {url}")

    monkeypatch.setattr(net, "open_url", offline)


@pytest.fixture
def station_dir(tmp_path: Path) -> Path:
    """Estación con los ejemplos de ``docs/documentacion`` (temario ``normativa``).

    Va en una subcarpeta para que ``tmp_path`` pueda hacer de disco externo.
    """
    root = tmp_path / "estacion"
    syllabus = root / "temarios" / "normativa"
    syllabus.mkdir(parents=True)
    shutil.copy(EXAMPLES / "atril.toml", root / "atril.toml")
    shutil.copy(EXAMPLES / "temario.toml", syllabus / "temario.toml")
    return root
