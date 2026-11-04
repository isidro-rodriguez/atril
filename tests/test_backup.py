import json
import shutil
import subprocess
from pathlib import Path
from typing import IO

import pytest
from support import write
from typer.testing import CliRunner

from atril import backup
from atril.backup import BackupError, BundleResult, Restic, Snapshot, Summary
from atril.commands import backup as commands
from atril.config import load_station
from atril.config.station import BackupTarget, Station
from atril.deeptutor import DeepTutor
from atril.main import app

runner = CliRunner()

STATION_BACKUP = """
[backup]
[backup.destinos.disco]
repo = "{disco}"
[backup.destinos.usb]
repo = "{usb}"
"""


@pytest.fixture
def station(station_dir: Path, tmp_path: Path) -> Station:
    """Estación con un destino accesible (disco) y otro desconectado (usb)."""
    text = (station_dir / "atril.toml").read_text(encoding="utf-8")
    text = text[: text.index("[backup]")] + STATION_BACKUP.format(
        disco=(tmp_path / "discoE" / "repo").as_posix(),
        usb=(tmp_path / "no-conectado" / "repo").as_posix(),
    )
    (station_dir / "atril.toml").write_text(text, encoding="utf-8")
    (tmp_path / "discoE").mkdir()
    write(station_dir / "data" / "user" / "settings.json", "{}")
    return load_station(station_dir)


def _target(station: Station, name: str) -> BackupTarget:
    return next(t for t in station.backup.targets if t.name == name)


# --- funciones puras -----------------------------------------------------------


def test_reachability(station: Station) -> None:
    assert backup.is_reachable(_target(station, "disco"))
    assert not backup.is_reachable(_target(station, "usb"))
    drive = BackupTarget("drive", "rclone:gdrive:Atril/restic")
    assert not backup.is_local(drive)
    assert backup.is_reachable(drive)


def test_password_from_environment() -> None:
    assert not backup.password_configured({})
    assert backup.password_configured({"RESTIC_PASSWORD_FILE": "C:/clave.txt"})


def test_backup_paths_and_git_repos(station: Station) -> None:
    (station.syllabi_dir / "normativa" / ".git").mkdir()

    assert backup.backup_paths(station) == [
        station.root / "atril.toml",
        station.data_dir,
        station.syllabi_dir,
    ]
    assert backup.git_repos(station) == {
        "temario-normativa": station.syllabi_dir / "normativa"
    }


def test_find_restored_root_and_swap(station: Station, tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    write(staging / "atril.toml", "restaurado")
    write(staging / "data" / "user" / "settings.json", '{"restaurado": true}')
    restored = backup.find_restored_root(staging)
    assert restored == staging
    (tmp_path / "vacio").mkdir()
    assert backup.find_restored_root(tmp_path / "vacio") is None

    keep = tmp_path / "previo"
    replaced = backup.swap_in(station, staging, keep)

    assert replaced == ["atril.toml", "data"]
    assert (station.root / "atril.toml").read_text() == "restaurado"
    assert (keep / "data" / "user" / "settings.json").read_text() == "{}"
    assert (station.syllabi_dir / "normativa" / "temario.toml").is_file()  # no tocado


def test_swap_rolls_back_on_failure(
    station: Station, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    write(staging / "atril.toml", "restaurado")
    write(staging / "data" / "x.txt", "nuevo")
    write(staging / "temarios" / "t" / "temario.toml", "nuevo")
    before = (station.root / "atril.toml").read_text()
    real_move = shutil.move

    def flaky(source: Path, target: Path) -> object:
        if Path(source).name == "temarios" and Path(source).parent == station.root:
            raise PermissionError("fichero en uso")
        return real_move(source, target)

    monkeypatch.setattr(backup.shutil, "move", flaky)

    with pytest.raises(BackupError, match="se ha deshecho"):
        backup.swap_in(station, staging, tmp_path / "previo")

    assert (station.root / "atril.toml").read_text() == before
    assert (station.data_dir / "user" / "settings.json").is_file()
    assert (staging / "data" / "x.txt").is_file()
    assert not (tmp_path / "previo").exists()


def test_parent_handles_windows_snapshot_paths() -> None:
    assert commands._parent("/D/Desarrollo/DeepTutor/data") == "D:/Desarrollo/DeepTutor"
    assert (
        commands._parent("D:\\Desarrollo\\DeepTutor\\data") == "D:/Desarrollo/DeepTutor"
    )
    assert commands._parent("/home/u/est/data") == "/home/u/est"


def test_path_findings_warn_on_other_root(station: Station) -> None:
    same = Snapshot("a", "t", (f"{station.root.as_posix()}/data",), "pc")
    other = Snapshot("b", "t", ("/otra/estacion/data",), "pc")

    assert commands._path_findings(station, same)[0].message.startswith(
        "El snapshot es"
    )
    assert "no coincidirán" in commands._path_findings(station, other)[0].message


# --- Restic con subprocess simulado --------------------------------------------


class FakeProcess:
    def __init__(self, lines: list[str], code: int = 0) -> None:
        self.stdout = iter(line + "\n" for line in lines)
        self.returncode = code

    def wait(self) -> int:
        return self.returncode


SUMMARY = json.dumps(
    {"message_type": "summary", "snapshot_id": "0123456789abcdef", "files_new": 1}
)


def _completed(
    code: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_ensure_repository(monkeypatch: pytest.MonkeyPatch, station: Station) -> None:
    calls: list[list[str]] = []
    codes = iter([backup.EXIT_NO_REPOSITORY, 0, 0, backup.EXIT_WRONG_PASSWORD])

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command[3:])
        return _completed(next(codes))

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    restic = Restic(_target(station, "disco"))

    assert restic.ensure_repository() is True
    assert calls == [["cat", "config"], ["init"]]
    assert restic.ensure_repository() is False
    with pytest.raises(BackupError, match="contraseña"):
        restic.ensure_repository()


def test_backup_parses_progress_and_summary(
    monkeypatch: pytest.MonkeyPatch, station: Station
) -> None:
    lines = [
        json.dumps(
            {
                "message_type": "status",
                "percent_done": 0.5,
                "bytes_done": 5,
                "total_bytes": 10,
            }
        ),
        "texto que no es json",
        json.dumps(
            {
                "message_type": "summary",
                "snapshot_id": "0123456789abcdef",
                "files_new": 3,
                "files_changed": 1,
                "data_added": 2048,
                "total_duration": 4.2,
            }
        ),
    ]
    seen: list[tuple[float, int, int]] = []
    commands_run: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        commands_run.append(command)
        return FakeProcess(lines)

    monkeypatch.setattr(backup.subprocess, "Popen", fake_popen)

    summary = Restic(_target(station, "disco")).backup(
        [station.data_dir], lambda *args: seen.append(args)
    )

    assert summary == Summary("01234567", 3, 1, 2048, 4.2)
    assert seen == [(0.5, 5, 10)]
    assert "--tag" in commands_run[0] and "*.part" in commands_run[0]


def test_backup_incomplete_on_code_3(
    monkeypatch: pytest.MonkeyPatch, station: Station
) -> None:
    unreadable = json.dumps(
        {
            "message_type": "error",
            "error": {"message": "access denied"},
            "item": "D:/est/data/x.db",
        }
    )
    monkeypatch.setattr(
        backup.subprocess,
        "Popen",
        lambda command, **kw: FakeProcess([unreadable, SUMMARY], code=3),
    )

    summary = Restic(_target(station, "disco")).backup([station.data_dir])

    assert summary.incomplete
    assert summary.unread == ("D:/est/data/x.db: access denied",)


def test_backup_error_detail_comes_from_stderr_file(
    monkeypatch: pytest.MonkeyPatch, station: Station
) -> None:
    def fake_popen(command: list[str], *, stderr: IO[str], **kw: object) -> FakeProcess:
        stderr.write("Fatal: unable to open repository\n")
        return FakeProcess([], code=1)

    monkeypatch.setattr(backup.subprocess, "Popen", fake_popen)

    with pytest.raises(BackupError, match="unable to open"):
        Restic(_target(station, "disco")).backup([station.data_dir])


def test_backup_failure(monkeypatch: pytest.MonkeyPatch, station: Station) -> None:
    error = json.dumps({"message_type": "error", "error": {"message": "disco lleno"}})
    monkeypatch.setattr(
        backup.subprocess, "Popen", lambda command, **kw: FakeProcess([error], code=1)
    )

    with pytest.raises(BackupError, match="disco lleno"):
        Restic(_target(station, "disco")).backup([station.data_dir])


# --- comandos ------------------------------------------------------------------


@pytest.fixture
def cli(station: Station, monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """restic y git simulados; DeepTutor parado."""
    calls: dict[str, list] = {
        "backup": [],
        "forget": [],
        "restore": [],
        "lifecycle": [],
    }
    monkeypatch.setenv("RESTIC_PASSWORD", "x")
    monkeypatch.setattr(commands.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: False)
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: False)
    monkeypatch.setattr(Restic, "ensure_repository", lambda self: True)

    def fake_backup(self: Restic, paths: list[Path], progress=None) -> Summary:
        calls["backup"].append(self.target.name)
        if progress:
            progress(1.0, 10, 10)
        return Summary("abcd1234", 2, 0, 1024, 1.0)

    monkeypatch.setattr(Restic, "backup", fake_backup)
    monkeypatch.setattr(
        Restic, "forget", lambda self, d, w, m: calls["forget"].append((d, w, m))
    )
    monkeypatch.setattr(commands.backup, "make_bundles", lambda station: [])
    return calls


def _invoke(station: Station, *args: str):
    return runner.invoke(
        app, ["backup", *args], env={"ATRIL_ESTACION": str(station.root)}
    )


def test_backup_skips_disconnected_disk(station: Station, cli: dict[str, list]) -> None:
    result = _invoke(station)

    assert result.exit_code == 0, result.output
    assert cli["backup"] == ["disco"]
    assert cli["forget"] == [(7, 4, 12)]
    assert "¿disco desconectado?" in result.output
    assert "abcd1234" in result.output


def test_incomplete_backup_skips_retention_and_fails(
    station: Station, cli: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Restic,
        "backup",
        lambda self, paths, progress=None: Summary(
            "abcd1234", 1, 0, 10, 1.0, unread=("x.db: bloqueado",)
        ),
    )

    result = _invoke(station)

    assert result.exit_code == 1
    assert cli["forget"] == []
    assert "INCOMPLETO" in result.output
    assert "x.db: bloqueado" in result.output
    assert "Backup terminado" not in result.output


def test_failed_declared_bundle_makes_backup_incomplete(
    station: Station, cli: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup, "git_repos", lambda station: {"repo-atril": Path()})
    monkeypatch.setattr(
        commands.backup,
        "make_bundles",
        lambda station: [
            BundleResult("temario-x", "sin commits"),
            BundleResult("repo-atril", "no es un repo", required=True),
        ],
    )

    result = _invoke(station)

    assert result.exit_code == 1
    assert cli["backup"] == ["disco"]
    assert "repos_git" in result.output


def test_backup_fails_if_requested_disk_is_missing(
    station: Station, cli: dict[str, list]
) -> None:
    result = _invoke(station, "--destino", "usb")

    assert result.exit_code == 1
    assert cli["backup"] == []


def test_backup_stops_and_restarts_deeptutor(
    station: Station, cli: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    write(station.deeptutor_cli, "")
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: True)
    monkeypatch.setattr(
        commands, "shutdown", lambda dt: cli["lifecycle"].append("parar")
    )
    monkeypatch.setattr(
        commands, "launch", lambda dt, timeout: cli["lifecycle"].append("arrancar")
    )

    result = _invoke(station)

    assert result.exit_code == 0, result.output
    assert cli["lifecycle"] == ["parar", "arrancar"]


def test_backup_requires_password(
    station: Station, cli: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RESTIC_PASSWORD")

    result = _invoke(station)

    assert result.exit_code == 1
    assert "RESTIC_PASSWORD" in result.output


def test_restore_command(
    station: Station, cli: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = Snapshot(
        "8b3931f2", "2026-11-03T15:43:12", (f"{station.root.as_posix()}/data",), "pc"
    )
    monkeypatch.setattr(Restic, "snapshots", lambda self: [snapshot])

    def fake_restore(self: Restic, snap: str, target: Path) -> None:
        cli["restore"].append(snap)
        write(target / "data" / "user" / "settings.json", '{"restaurado": true}')

    monkeypatch.setattr(Restic, "restore", fake_restore)

    result = _invoke(station, "restaurar", "-d", "disco", "--si")

    assert result.exit_code == 0, result.output
    assert cli["restore"] == ["8b3931f2"]
    assert '"restaurado"' in (station.data_dir / "user" / "settings.json").read_text()
    kept = list(station.root.parent.glob(f"{station.root.name}.previo-*"))
    assert len(kept) == 1
    assert not list(station.root.parent.glob(f"{station.root.name}.restaurar-*"))


def test_restore_from_other_path_needs_flag(
    station: Station, cli: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = Snapshot("8b3931f2", "2026-11-03T15:43:12", ("/otra/est/data",), "pc")
    monkeypatch.setattr(Restic, "snapshots", lambda self: [snapshot])
    monkeypatch.setattr(
        Restic, "restore", lambda self, snap, target: cli["restore"].append(snap)
    )

    blocked = _invoke(station, "restaurar", "-d", "disco", "--si")
    assert blocked.exit_code == 1
    assert "--nueva-ruta" in blocked.output
    assert cli["restore"] == []

    forced = _invoke(station, "restaurar", "-d", "disco", "--si", "--nueva-ruta")
    assert cli["restore"] == ["8b3931f2"]
    assert "estación reconocible" in forced.output  # el restore simulado no deja nada


# --- integración con restic real -----------------------------------------------


@pytest.mark.skipif(shutil.which("restic") is None, reason="restic no instalado")
def test_real_restic_roundtrip(
    station: Station, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RESTIC_PASSWORD", "prueba")
    restic = Restic(_target(station, "disco"), shutil.which("restic") or "restic")

    assert restic.ensure_repository() is True
    summary = restic.backup(backup.backup_paths(station))
    assert summary.files_new >= 2
    restic.check()
    snapshots = restic.snapshots()
    assert len(snapshots) == 1

    target = tmp_path / "restaurado"
    restic.restore(snapshots[0].short_id, target)
    restored = backup.find_restored_root(target)
    assert restored is not None
    assert (restored / "data" / "user" / "settings.json").read_text() == "{}"
    restic.forget(7, 4, 12)
