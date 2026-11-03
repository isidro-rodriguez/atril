"""Datos y utilidades compartidos por las pruebas."""

from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "ejemplos"

MINIMAL_STATION = """
[deeptutor]
[ollama]
embedding = "qwen3-embedding:8b"
dimension = 4096
[backup.destinos.disco]
repo = 'E:\\restic-atril'
"""


def write(path: Path, text: str) -> Path:
    """Escribe ``text`` en ``path`` creando las carpetas que falten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
