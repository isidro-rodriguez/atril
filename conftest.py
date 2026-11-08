"""Configuración de pytest en la raíz: el doctest de ``src/`` y la GUI.

Sin ``tkinter`` (Python de Linux sin Tk) no se pueden importar los módulos de la
ventana; se omiten al recoger los doctest de ``src/``.
"""

import importlib.util

collect_ignore_glob = (
    []
    if importlib.util.find_spec("tkinter")
    else ["src/atril/gui/app.py", "src/atril/gui/style.py"]
)
