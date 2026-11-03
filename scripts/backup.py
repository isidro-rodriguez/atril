"""Copia de seguridad del repositorio con `git bundle`.

Crea en la raíz `<proyecto>-<AAAA-MM-DD_HH-MM-SS>.bundle` con todas las ramas y
etiquetas. El nombre del proyecto se lee de `pyproject.toml`.

Uso:
    poe backup
    uv run python scripts/backup.py
"""

import subprocess
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _project_name() -> str:
    """Nombre del proyecto declarado en `[project].name` de `pyproject.toml`."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["name"])


def main() -> None:
    """Crea la copia de seguridad en la raíz del repositorio e informa de su ruta.

    Raises:
        FileNotFoundError: Si falta `pyproject.toml` o `git` no está instalado.
        tomllib.TOMLDecodeError: Si `pyproject.toml` no es TOML válido.
        KeyError: Si `pyproject.toml` no declara `[project].name`.
        subprocess.CalledProcessError: Si `git bundle` termina con error.
    """
    target = ROOT / f"{_project_name()}_{datetime.now():%Y-%m-%d_%H-%M-%S}.bundle"
    # cwd explícito: git debe operar sobre este repo aunque se lance desde otro sitio.
    subprocess.run(
        ["git", "bundle", "create", str(target), "--all"], cwd=ROOT, check=True
    )
    print(f"Copia creada en {target}")


if __name__ == "__main__":
    main()
