"""Fixtures comunes de las pruebas."""

import shutil
from pathlib import Path

import pytest
from support import EXAMPLES


@pytest.fixture
def station_dir(tmp_path: Path) -> Path:
    """Estación con los ficheros de ``docs/ejemplos`` (temario ``normativa``).

    Va en una subcarpeta para que ``tmp_path`` pueda hacer de disco externo.
    """
    root = tmp_path / "estacion"
    syllabus = root / "temarios" / "normativa"
    syllabus.mkdir(parents=True)
    shutil.copy(EXAMPLES / "atril.toml", root / "atril.toml")
    shutil.copy(EXAMPLES / "temario.toml", syllabus / "temario.toml")
    return root
