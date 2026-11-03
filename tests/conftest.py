"""Fixtures comunes de las pruebas."""

import shutil
from pathlib import Path

import pytest
from support import EXAMPLES


@pytest.fixture
def station_dir(tmp_path: Path) -> Path:
    """Estación con los ficheros de ``docs/ejemplos`` (temario ``normativa``)."""
    shutil.copy(EXAMPLES / "atril.toml", tmp_path / "atril.toml")
    syllabus = tmp_path / "temarios" / "normativa"
    syllabus.mkdir(parents=True)
    shutil.copy(EXAMPLES / "temario.toml", syllabus / "temario.toml")
    return tmp_path
