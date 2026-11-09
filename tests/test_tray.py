"""Pruebas de la espera al instalador (sin Windows: se simula su mutex)."""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from atril.gui import app, tray


def test_wait_for_setup_until_mutex_disappears(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter([True, True, False])
    clock = iter([0.0, 1.0, 2.0, 3.0])
    monkeypatch.setattr(tray, "setup_running", lambda: next(states))
    _fake_time(monkeypatch, clock)
    assert tray.wait_for_setup(timeout=10)


def test_wait_for_setup_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 5.0, 11.0])
    monkeypatch.setattr(tray, "setup_running", lambda: True)
    _fake_time(monkeypatch, clock)
    assert not tray.wait_for_setup(timeout=10)


def _fake_time(monkeypatch: pytest.MonkeyPatch, clock: Iterator[float]) -> None:
    """Reloj falso solo para ``tray`` (sin tocar el ``time`` de todo el proceso)."""
    fake = SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None)
    monkeypatch.setattr(tray, "time", fake)


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
