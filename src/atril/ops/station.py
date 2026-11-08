r"""Estación del equipo: dónde está y cómo se recuerda.

Hay una sola estación por equipo, guardada en la variable de usuario
``ATRIL_ESTACION``. En Windows se escribe directamente en el registro del usuario
(``HKCU\Environment``), sin abrir consolas; atril no tiene fichero propio.
"""

import os
import sys
from pathlib import Path

from atril.checks import Finding, info, ok, warning

STATION_VARIABLE = "ATRIL_ESTACION"
"""Variable de usuario con la raíz de la única estación del equipo."""

_ENVIRONMENT_KEY = "Environment"
"""Clave del registro con las variables de entorno del usuario."""


def saved_station() -> Path | None:
    """Estación guardada: del entorno o, en Windows, del registro del usuario.

    Un terminal abierto antes de guardarla no la tiene en su entorno; por eso,
    si falta, se lee del registro.
    """
    value = os.environ.get(STATION_VARIABLE)
    if not value and sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY) as key:
                value, _ = winreg.QueryValueEx(key, STATION_VARIABLE)
        except OSError:
            value = None
    return Path(str(value)) if value else None


def persist_station(root: Path) -> Finding:
    """Guarda ``ATRIL_ESTACION`` para este proceso y para el usuario.

    En Windows la escribe en el registro del usuario y avisa a las ventanas
    abiertas (``WM_SETTINGCHANGE``), como hace ``setx``. En otros sistemas indica
    la línea para el perfil de la shell.
    """
    os.environ[STATION_VARIABLE] = str(root)
    if sys.platform != "win32":
        return info(f"Añade a tu perfil de shell: export {STATION_VARIABLE}={root}")
    try:
        _write_registry(str(root))
    except OSError:
        return warning(
            f"No se ha podido guardar {STATION_VARIABLE}; hazlo con: "
            f'setx {STATION_VARIABLE} "{root}"'
        )
    return ok(f"Estación guardada: {root} (variable de usuario {STATION_VARIABLE}).")


def _write_registry(value: str) -> None:
    r"""Escribe la variable en ``HKCU\Environment`` y lo anuncia (solo Windows)."""
    if sys.platform != "win32":
        return
    import ctypes
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _ENVIRONMENT_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, STATION_VARIABLE, 0, winreg.REG_SZ, value)
    hwnd_broadcast, wm_settingchange, smto_abortifhung = 0xFFFF, 0x001A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        hwnd_broadcast,
        wm_settingchange,
        0,
        _ENVIRONMENT_KEY,
        smto_abortifhung,
        5000,
        None,
    )
