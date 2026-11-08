"""Prueba de humo de la ventana, en un proceso aparte.

Python 3.14 en Windows puede fallar al cerrar el intérprete después de usar Tk,
aunque la prueba haya ido bien; en un proceso aparte que termina con
``os._exit`` eso no afecta al resto de pruebas.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("tkinter")

SCRIPT = textwrap.dedent(
    """
    import os, sys, tkinter as tk
    from pathlib import Path

    try:
        tk.Tk().destroy()
    except tk.TclError:
        print("SIN-PANTALLA")
        os._exit(0)

    from atril.checks import ok
    from atril.config import load_station
    from atril.config.station import init_station
    from atril.gui.app import App
    from atril.gui.home import HomeView
    from atril.gui.syllabi import SyllabiView
    from atril.ops import service
    from atril.ops import syllabus as syllabus_ops

    root = Path(sys.argv[1])
    init_station(root)
    station = load_station(root)
    syllabus_ops.create(station, "Física")
    sections = [("DeepTutor", [ok("Instalado."), ok("En marcha: http://x")])]
    service.status = lambda station, reporter: sections

    def settle(app):
        thread = app.worker._thread
        if thread is not None:
            thread.join(timeout=5)
        app.worker.poll()

    app = App(station)
    settle(app)
    home = app.views["Inicio"]
    assert isinstance(home, HomeView)
    assert "Atril está listo" in str(home._overall.cget("text"))
    assert home._rows.winfo_children()

    app.show_view("Temarios")
    settle(app)
    syllabi = app.views["Temarios"]
    assert isinstance(syllabi, SyllabiView)
    assert syllabi._list.get_children() == ("fisica",)
    assert "Física" in str(syllabi._title.cget("text"))
    app.destroy()
    print("VENTANA-OK", flush=True)
    os._exit(0)
    """
)


def test_main_window_home_and_syllabi(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path / "estacion")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if "SIN-PANTALLA" in result.stdout:
        pytest.skip("sin pantalla")
    assert "VENTANA-OK" in result.stdout, result.stderr
    assert result.returncode == 0
