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

    from atril.checks import Level, ok
    from atril.config import load_station
    from atril.config.station import init_station
    from atril.gui.app import App
    from atril.gui.home import HomeView
    from atril.gui.syllabi import SyllabiView
    from atril.ops import service
    from atril.ops import syllabus as syllabus_ops

    root = Path(sys.argv[1])
    init_station(root)
    copies = root.parent / "copias"
    copies.mkdir()
    (copies / "atril-20261108-090000.zip").write_bytes(b"x")
    config = root / "atril.toml"
    text = config.read_text(encoding="utf-8")
    start = text.index("destinos = [")
    end = text.index("]", start) + 1
    text = text[:start] + f"destinos = [{copies.as_posix()!r}]" + text[end:]
    config.write_text(text, encoding="utf-8")
    station = load_station(root)

    from atril import ollama
    from atril.ops import installation as installation_ops
    from atril.ops.installation import Tool

    installation_ops.tools = lambda: [Tool("git", "/usr/bin/git", True)]
    ollama.get_status = lambda url, timeout=3.0: ollama.OllamaStatus(False)
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
    assert str(home._headline.cget("text")) == "Preparado"
    assert home._rows.winfo_children()
    assert home._recent.winfo_children()  # el temario recién creado

    app.show_view("Temarios")
    settle(app)
    syllabi = app.views["Temarios"]
    assert isinstance(syllabi, SyllabiView)
    assert syllabi._list.get_children() == ("fisica",)
    assert "Física" in str(syllabi._title.cget("text"))

    app.show_view("Copias")
    settle(app)
    copies_view = app.views["Copias"]
    assert len(copies_view._table.get_children()) == 1

    # Volver a un apartado ya leído no vuelve a consultar nada.
    calls = []
    copies_view.refresh = lambda: calls.append(1) or True
    app.show_view("Inicio")
    app.show_view("Copias")
    assert calls == []
    app.log(Level.INFO, "x")  # no es una operación: no caduca nada
    app.show_view("Copias")
    assert calls == []

    app.show_view("Biblioteca")
    settle(app)
    assert app.views["Biblioteca"]._table.get_children() == ()  # temario vacío

    app.show_view("Servicios")
    settle(app)
    assert app.views["Servicios"]._tools.winfo_children()

    app.show_view("Diagnóstico")
    settle(app)
    report = app.views["Diagnóstico"]._status.get("1.0", "end")
    assert "Estación:" in report and "git: /usr/bin/git" in report
    app.log(Level.WARNING, "Aviso de prueba")
    app._show_history()
    assert app.views["Diagnóstico"]._history.get_children()

    app.show_view("Ajustes")
    settings = app.views["Ajustes"]
    settings._keep.set(3)
    settings.save()
    assert app.station.backup.keep == 3
    assert "conservar = 3" in config.read_text(encoding="utf-8")

    # Cerrar con una operación en marcha: se cancela y se espera; no se corta.
    import threading
    from tkinter import messagebox
    from atril.errors import CancelledError

    messagebox.askyesno = lambda *args, **kwargs: True
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
