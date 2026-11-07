"""Datos y utilidades compartidos por las pruebas."""

from pathlib import Path

from atril.patches import PATCHES

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "ejemplos"

MINIMAL_STATION = """
[deeptutor]
[ollama]
embedding = "qwen3-embedding:8b"
dimension = 4096
[backup]
destinos = ['E:\\backups-atril']
"""


def write(path: Path, text: str) -> Path:
    """Escribe ``text`` en ``path`` creando las carpetas que falten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_other_patches(app_dir: Path, skip: str) -> None:
    """Deja pendientes (texto original) los ficheros de los parches salvo ``skip``."""
    for name, patch in PATCHES.items():
        if name != skip:
            write(app_dir / patch.file, f"x = {{{patch.old}}}\n")
