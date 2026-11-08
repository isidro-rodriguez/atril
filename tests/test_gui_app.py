import gc
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from atril.checks import ok  # noqa: E402
from atril.config import load_station  # noqa: E402
from atril.config.station import init_station  # noqa: E402
from atril.ops import service  # noqa: E402


@pytest.fixture
def display() -> None:
    """Salta la prueba si no hay pantalla (CI de Linux)."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("sin pantalla")
    root.destroy()
    del root
    gc.collect()  # Tk debe liberarse en el hilo principal, no en el de otro test


def _settle(app) -> None:
    """Espera al trabajo en curso y reparte sus avisos."""
    thread = app.worker._thread
    if thread is not None:
        thread.join(timeout=5)
    app.worker.poll()


def test_main_window_home_and_syllabi(
    display: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.gui.app import App
    from atril.gui.home import HomeView
    from atril.gui.syllabi import SyllabiView
    from atril.ops import syllabus as syllabus_ops

    init_station(tmp_path / "estacion")
    station = load_station(tmp_path / "estacion")
    syllabus_ops.create(station, "Física")
    sections = [("DeepTutor", [ok("Instalado."), ok("En marcha: http://x")])]
    monkeypatch.setattr(service, "status", lambda station, reporter: sections)
    app = App(station)
    try:
        _settle(app)
        home = app.views["Inicio"]
        assert isinstance(home, HomeView)
        assert "Atril está listo" in str(home._overall.cget("text"))
        assert home._rows.winfo_children()

        app.show_view("Temarios")
        _settle(app)
        syllabi = app.views["Temarios"]
        assert isinstance(syllabi, SyllabiView)
        assert syllabi._list.get_children() == ("fisica",)
        assert "Física" in str(syllabi._title.cget("text"))
    finally:
        app.destroy()
        del app
        gc.collect()
