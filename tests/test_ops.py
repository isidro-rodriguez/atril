import contextlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import backup, lock, processes
from atril.config import load_station
from atril.config.station import Station
from atril.deeptutor import DeepTutor, Orphans
from atril.errors import AtrilError, CancelledError
from atril.lock import BusyError, station_lock
from atril.main import app
from atril.ops import Recorder, service
from atril.ops import backup as operations
from atril.ops import station as station_ops

runner = CliRunner()


@pytest.fixture
def station(station_dir: Path, tmp_path: Path) -> Station:
    """Estación con un destino de copias accesible y DeepTutor parado."""
    text = (station_dir / "atril.toml").read_text(encoding="utf-8")
    folder = (tmp_path / "disco" / "atril").as_posix()
    text = text[: text.index("[backup]")] + f"[backup]\ndestinos = ['{folder}']\n"
    (station_dir / "atril.toml").write_text(text, encoding="utf-8")
    (tmp_path / "disco").mkdir()
    write(station_dir / "data" / "user" / "settings.json", "{}")
    return load_station(station_dir)


@pytest.fixture
def idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: False)
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: False)


@contextlib.contextmanager
def _held_elsewhere(station: Station):
    """Bloqueo tomado por otro «proceso» (otro descriptor), con su ficha."""
    fd = os.open(station.lock_file, os.O_RDWR | os.O_CREAT)
    try:
        assert lock.try_lock(fd)
        holder = {"pid": 4242, "operacion": "indexado", "desde": "hoy"}
        os.write(fd, json.dumps(holder).encode())
        yield
    finally:
        lock.unlock(fd)
        os.close(fd)


# --- bloqueo -------------------------------------------------------------------


def test_lock_is_released_and_reentrant(station: Station) -> None:
    with station_lock(station, "copia"):
        holder = json.loads(station.lock_file.read_text(encoding="utf-8"))
        assert holder["operacion"] == "copia"
        with station_lock(station, "arranque"):  # la misma operación anida otra
            pass
    fd = os.open(station.lock_file, os.O_RDWR)
    try:
        assert lock.try_lock(fd)  # liberado al salir
    finally:
        lock.unlock(fd)
        os.close(fd)


def test_lock_held_elsewhere_is_busy(station: Station) -> None:
    with (
        _held_elsewhere(station),
        pytest.raises(BusyError, match=r"indexado \(PID 4242"),
        station_lock(station, "copia"),
    ):
        pass


def test_leftover_lock_file_does_not_block(station: Station) -> None:
    station.lock_file.write_text('{"pid": 1, "operacion": "vieja"}', "utf-8")

    with station_lock(station, "copia"):  # nadie lo tiene: el fichero no basta
        assert "copia" in station.lock_file.read_text(encoding="utf-8")


def test_lock_released_when_process_dies(station: Station) -> None:
    script = (
        "import os, sys; from atril import lock; "
        "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT); "
        "assert lock.try_lock(fd); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", script, str(station.lock_file)], check=True)

    with station_lock(station, "copia"):
        pass


def test_backup_command_refuses_busy_station(station: Station, idle: None) -> None:
    with _held_elsewhere(station):
        result = runner.invoke(
            app, ["backup"], env={"ATRIL_ESTACION": str(station.root)}
        )

    assert result.exit_code == 1
    assert "ocupada" in result.output
    assert not backup.archives(station.backup.destinations[0])


# --- copias ---------------------------------------------------------------------


def test_create_returns_result_without_console(station: Station, idle: None) -> None:
    recorder = Recorder()

    created = operations.create(station, recorder)

    assert created.archive.is_file()
    assert created.files >= 2
    assert "Comprimiendo" in recorder.steps
    assert any("verificada" in f.message for f in recorder.findings)
    _assert_free(station)


def test_cancelled_backup_leaves_nothing(station: Station, idle: None) -> None:
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(CancelledError):
        operations.create(station, Recorder(), cancel=cancel)

    assert not list(station.backup.destinations[0].iterdir())
    _assert_free(station)


def test_restore_plan_refuses_running_deeptutor(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(station.deeptutor_cli, "")
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: True)

    with pytest.raises(AtrilError, match="en marcha"):
        operations.plan_restore(station, Recorder())


# --- servicio y estación --------------------------------------------------------


def test_start_error_carries_launcher_log(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(station.launcher_log, "linea\nfallo del build\n")
    monkeypatch.setattr(service, "ensure_ollama", lambda station, reporter: [])
    monkeypatch.setattr(DeepTutor, "orphans", lambda self: Orphans((), ()))
    monkeypatch.setattr(DeepTutor, "start", lambda self: 1)

    with pytest.raises(AtrilError) as caught:
        service.start(DeepTutor(station), Recorder(), timeout=10)

    assert caught.value.log[-1] == "fallo del build"
    assert caught.value.log_title == str(station.launcher_log)


def test_persist_station_outside_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv(station_ops.STATION_VARIABLE, raising=False)

    finding = station_ops.persist_station(tmp_path)

    assert "export ATRIL_ESTACION=" in finding.message
    assert os.environ[station_ops.STATION_VARIABLE] == str(tmp_path)
    assert station_ops.saved_station() == tmp_path


def test_no_window_only_without_console(monkeypatch: pytest.MonkeyPatch) -> None:
    assert processes.no_window() == 0  # pytest tiene consola

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", None)
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    assert processes.no_window() == flag


def _assert_free(station: Station) -> None:
    """Nadie tiene el bloqueo de la estación."""
    fd = os.open(station.lock_file, os.O_RDWR | os.O_CREAT)
    try:
        assert lock.try_lock(fd)
    finally:
        lock.unlock(fd)
        os.close(fd)
