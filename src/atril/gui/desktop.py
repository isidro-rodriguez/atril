"""Abrir carpetas y ficheros con la aplicación del sistema."""

import os
import sys
import webbrowser
from pathlib import Path


def open_path(path: Path) -> None:
    """Abre ``path`` con su aplicación (explorador, editor de texto...)."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        webbrowser.open(path.as_uri())
