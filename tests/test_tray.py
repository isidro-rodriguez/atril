"""Pruebas de la espera al instalador (sin Windows: se simula su mutex)."""

import pytest

from atril.gui import app, tray


def test_wait_for_setup_until_mutex_disappears(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter([True, True, False])
    clock = iter([0.0, 1.0, 2.0, 3.0])
    monkeypatch.setattr(tray, "setup_running", lambda: next(states))
    monkeypatch.setattr(tray.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tray.time, "sleep", lambda _: None)
    assert tray.wait_for_setup(timeout=10)


def test_wait_for_setup_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 5.0, 11.0])
    monkeypatch.setattr(tray, "setup_running", lambda: True)
    monkeypatch.setattr(tray.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tray.time, "sleep", lambda _: None)
    assert not tray.wait_for_setup(timeout=10)


@pytest.mark.parametrize(
    ("argv", "running", "waited"),
    [
        (["atril-gui"], True, None),  # abierta a mitad de la instalación: no se abre
        (["atril-gui", app.AFTER_SETUP], True, False),  # el instalador no termina
    ],
)
def test_run_does_not_open_during_setup(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    running: bool,
    waited: bool | None,
) -> None:
    monkeypatch.setattr(app.sys, "argv", argv)
    monkeypatch.setattr(tray, "setup_running", lambda: running)
    monkeypatch.setattr(tray, "wait_for_setup", lambda: waited)

    def opened() -> bool:
        raise AssertionError("no debe abrir la ventana")

    monkeypatch.setattr(tray, "signal_running", opened)
    app.run()
