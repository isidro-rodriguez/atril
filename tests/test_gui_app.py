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


def test_main_window_shows_status(
    display: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.gui.app import App

    init_station(tmp_path / "estacion")
    sections = [("DeepTutor", [ok("Instalado."), ok("En marcha: http://x")])]
    monkeypatch.setattr(service, "status", lambda station, reporter: sections)
    app = App(load_station(tmp_path / "estacion"))
    try:
        thread = app.worker._thread
        assert thread is not None
        thread.join(timeout=5)
        app.worker.poll()
        assert "Atril está listo" in str(app._overall.cget("text"))
        assert app._rows.winfo_children()
    finally:
        app.destroy()
        del app
        gc.collect()
