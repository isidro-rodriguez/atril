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
        print("SIN-PANTALLA", flush=True)
        os._exit(0)

    from atril.checks import Level
    from atril.config import load_station
    from atril.config.station import init_station
    from atril.gui import app as app_module
    from atril.gui.app import App
    from atril.gui.home import HomeView
    from atril.gui.library import LibraryView
    from atril.gui.syllabi import SyllabiView
    from atril.ops import syllabus as syllabus_ops

    root = Path(sys.argv[1])
    init_station(root)
    copies = root.parent / "copias"
    copies.mkdir()
    (copies / "atril-20261108-090000.zip").write_bytes(b"x")
    (copies / "atril-20261101-090000.zip").write_bytes(b"xx")
    config = root / "atril.toml"
    text = config.read_text(encoding="utf-8")
    start = text.index("destinos = [")
    end = text.index("]", start) + 1
    text = text[:start] + f"destinos = [{copies.as_posix()!r}]" + text[end:]
    config.write_text(text, encoding="utf-8")
    station = load_station(root)

    from atril import ollama

    ollama.get_status = lambda url, timeout=3.0: ollama.OllamaStatus(False)
    syllabus_ops.create(station, "Física")
    syllabus_ops.create(station, "Historia")

    def settle(app):
        thread = app.worker._thread
        if thread is not None:
            thread.join(timeout=5)
        app.worker.poll()

    app = App(station)
    settle(app)
    factor = app.tk.call("tk", "scaling") / (96 / 72)
    assert not app.resizable()[0] and not app.resizable()[1]  # ventana fija
    home = app.views["Inicio"]
    assert isinstance(home, HomeView)
    assert str(home._headline.cget("text")) == "Necesita atención"  # sin instalar
    assert str(home._toggle.cget("text")) == "Instalar DeepTutor"
    assert [t._card.key for t in home._tiles][0] == "deeptutor"

    app.show_view("Temarios")
    settle(app)
    syllabi = app.views["Temarios"]
    assert isinstance(syllabi, SyllabiView)
    assert syllabi._picker.combo.cget("values") == ("Física", "Historia")
    assert "Física" in str(syllabi._title.cget("text"))

    # El temario elegido se comparte con la Biblioteca y se recuerda.
    syllabi._picker.combo.current(1)
    syllabi._picker._changed(None)
    assert app.syllabus_id == "historia"
    app.show_view("Biblioteca")
    settle(app)
    library = app.views["Biblioteca"]
    assert isinstance(library, LibraryView)
    assert library._picker.combo.get() == "Historia"
    assert "historia" in station.window_state_file.read_text(encoding="utf-8")

    app.show_view("Backups")
    settle(app)
    backups = app.views["Backups"]
    first = lambda: backups._table.item(backups._table.get_children()[0], "values")[0]
    assert "8 nov" in first()  # el más reciente arriba
    backups._sorter.sort(0)  # clic en «Fecha»: ascendente
    assert "1 nov" in first()
    backups._sorter.sort(0)  # otro clic: descendente
    assert "8 nov" in first()
    backups._sorter.sort(1)  # por tamaño, ascendente
    assert "8 nov" in first()

    # Volver a un apartado ya leído no vuelve a consultar nada.
    calls = []
    backups.refresh = lambda: calls.append(1) or True
    app.show_view("Inicio")
    app.show_view("Backups")
    assert calls == []
    app.log(Level.INFO, "x")  # no es una operación: no caduca nada
    app.show_view("Backups")
    assert calls == []

    app.log(Level.WARNING, "Aviso de prueba")
    app.show_view("Actividad")
    assert app.views["Actividad"]._list.get_children()

    # Ajustes: un cambio sencillo se guarda sin preguntar nada más.
    app.show_view("Ajustes")
    settings = app.views["Ajustes"]
    settings._vars[("backup", "conservar")].set("3")
    settings.save()
    assert app.station.backup.keep == 3
    assert "conservar = 3" in config.read_text(encoding="utf-8")
    assert settings.changes() == {}

    # Cerrar con una operación en marcha: se cancela y se espera; no se corta.
    import threading
    from atril.errors import CancelledError

    app_module.ask_yes_no = lambda *args, **kwargs: True
    started = threading.Event()

    def slow(reporter):
        started.set()
        app.worker.cancel.wait(5)
        raise CancelledError("cancelado en un punto seguro")

    app.run("Operación lenta", slow, lambda _: None)
    started.wait(5)
    app.close()
    assert not app.closed  # sigue abierta mientras el trabajo no termina
    app.worker._thread.join(5)
    app._poll()
    assert app.closed
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
