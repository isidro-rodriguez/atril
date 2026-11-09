"""Comando ``atril gui``: abre la ventana sin ocupar la consola."""

import subprocess
import sys
from pathlib import Path

from atril import processes
from atril.commands._common import success

_DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def gui_command() -> list[str]:
    """Línea de comandos que abre la ventana con el Python de atril.

    En Windows usa ``pythonw.exe`` (sin consola), igual que ``atril-gui``.
    """
    python = Path(sys.executable)
    if sys.platform == "win32" and python.name.lower() == "python.exe":
        windowless = python.with_name("pythonw.exe")
        if windowless.is_file():
            python = windowless
    return [str(python), "-c", "from atril.gui import main; main()"]


def open_gui() -> None:
    """Abre la ventana de atril y devuelve la consola en el acto.

    Si la ventana ya está abierta (u oculta en el área de notificación), se
    muestra esa.
    """
    windows = sys.platform == "win32"
    subprocess.Popen(
        gui_command(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=_DETACHED | processes.no_window() if windows else 0,
        start_new_session=not windows,
    )
    success("Ventana de atril abierta.")
