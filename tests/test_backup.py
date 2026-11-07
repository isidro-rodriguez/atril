import json
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import backup
from atril.backup import BackupError
from atril.commands import backup as commands
from atril.config import load_station
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.main import app

runner = CliRunner()


def _station(station_dir: Path, tmp_path: Path, archive_format: str = "zip") -> Station:
    """Estación con un destino accesible (discoE) y otro desconectado (usb)."""
    text = (station_dir / "atril.toml").read_text(encoding="utf-8")
    disco = (tmp_path / "discoE" / "atril").as_posix()
    usb = (tmp_path / "no-conectado" / "atril").as_posix()
    text = text[: text.index("[backup]")] + (
        f"[backup]\ndestinos = ['{disco}', '{usb}']\n"
        f"formato = '{archive_format}'\nconservar = 2\n"
    )
    (station_dir / "atril.toml").write_text(text, encoding="utf-8")
    (tmp_path / "discoE").mkdir()
    write(station_dir / "data" / "user" / "settings.json", '{"tema": "claro"}')
    write(station_dir / "data" / "atril" / "logs" / "indexado.log", "ruido")
    write(station_dir / "data" / "knowledge_bases" / "cte" / "x.part", "a medias")
    write(station_dir / "app" / "pyproject.toml", "no se copia")
    return load_station(station_dir)


@pytest.fixture
def station(station_dir: Path, tmp_path: Path) -> Station:
    return _station(station_dir, tmp_path)


def _folder(station: Station) -> Path:
    return station.backup.destinations[0]


# --- módulo backup -------------------------------------------------------------


def test_station_files_skip_app_logs_and_partial(station: Station) -> None:
    names = {name for _, name in backup.station_files(station)}

    assert "atril.toml" in names
    assert "data/user/settings.json" in names
    assert "temarios/normativa/temario.toml" in names
    assert not any(name.startswith(("app/", "data/atril/logs/")) for name in names)
    assert not any(name.endswith(".part") for name in names)


@pytest.mark.parametrize("archive_format", ["zip", "tar.xz"])
def test_create_verify_and_extract(
    station_dir: Path, tmp_path: Path, archive_format: str
) -> None:
    station = _station(station_dir, tmp_path, archive_format)
    seen: list[int] = []

    result = backup.create(station, _folder(station), seen.append)

    assert result.archive.name.endswith(backup.EXTENSIONS[archive_format])
    assert not result.incomplete
    assert sum(seen) == result.read_bytes
    assert not list(_folder(station).glob("*.part"))
    manifest = backup.verify(result.archive)
    assert manifest["estacion"] == str(station.root)

    target = tmp_path / "extraido"
    assert backup.extract(result.archive, target)["estacion"] == str(station.root)
    assert (target / "data" / "user" / "settings.json").read_text() == (
        '{"tema": "claro"}'
    )
    assert not (target / backup.MANIFEST).exists()


def test_verify_detects_damage(station: Station) -> None:
    archive = backup.create(station, _folder(station)).archive
    data = archive.read_bytes()
    archive.write_bytes(data[: len(data) // 2])

    with pytest.raises(BackupError, match="dañada"):
        backup.verify(archive)


def test_extract_rejects_paths_outside(tmp_path: Path) -> None:
    evil = tmp_path / "atril-20260101-000000.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("../fuera.txt", "x")
        archive.writestr(backup.MANIFEST, "{}")

    with pytest.raises(BackupError, match="ruta no permitida"):
        backup.extract(evil, tmp_path / "destino")
    assert not (tmp_path / "fuera.txt").exists()


def test_extract_tar_rejects_paths_outside(tmp_path: Path) -> None:
    evil = tmp_path / "atril-20260101-000000.tar.xz"
    payload = tmp_path / "carga.txt"
    payload.write_text("x")
    with tarfile.open(evil, "w:xz") as archive:
        archive.add(payload, "../fuera.txt")

    with pytest.raises(BackupError):
        backup.extract(evil, tmp_path / "destino")
    assert not (tmp_path / "fuera.txt").exists()


def test_archives_and_prune(tmp_path: Path) -> None:
    for stamp in ("20261101-010000", "20261103-010000", "20261102-010000"):
        write(tmp_path / backup.archive_name("zip", stamp), "x")
    write(tmp_path / "otra-cosa.zip", "no es de atril")

    assert [a.stamp for a in backup.archives(tmp_path)] == [
        "20261101-010000",
        "20261102-010000",
        "20261103-010000",
    ]
    removed = backup.prune(tmp_path, 2)
    assert [path.name for path in removed] == ["atril-20261101-010000.zip"]
    assert (tmp_path / "otra-cosa.zip").exists()


def test_reachability(tmp_path: Path) -> None:
    assert backup.is_reachable(tmp_path / "nueva")
    assert not backup.is_reachable(tmp_path / "no-conectado" / "atril")


def test_find_swap_rolls_back_on_failure(
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
    assert (staging / "data" / "x.txt").is_file()
    assert not (tmp_path / "previo").exists()


# --- comandos ------------------------------------------------------------------


@pytest.fixture
def idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """DeepTutor parado."""
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: False)
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: False)


def _invoke(station: Station, *args: str, input: str | None = None):
    env = {"ATRIL_ESTACION": str(station.root)}
    return runner.invoke(app, ["backup", *args], env=env, input=input)


def test_backup_command_skips_disconnected_disk(station: Station, idle: None) -> None:
    result = _invoke(station)

    assert result.exit_code == 0, result.output
    assert "¿disco desconectado?" in result.output
    assert "Backup terminado" in result.output
    assert len(backup.archives(_folder(station))) == 1


def test_backup_copies_to_every_destination_and_prunes(
    station_dir: Path, tmp_path: Path, idle: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = _station(station_dir, tmp_path)
    (tmp_path / "no-conectado").mkdir()  # el segundo disco ya está conectado
    stamps = iter(["20261101-010000", "20261102-010000", "20261103-010000"])
    real_name = backup.archive_name
    monkeypatch.setattr(
        backup, "archive_name", lambda fmt, stamp=None: real_name(fmt, next(stamps))
    )

    for _ in range(3):
        assert _invoke(station).exit_code == 0

    for folder in station.backup.destinations:
        assert [a.stamp for a in backup.archives(folder)] == [
            "20261102-010000",
            "20261103-010000",
        ]


def test_unreadable_file_makes_backup_incomplete(
    station: Station, idle: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(_folder(station) / backup.archive_name("zip", "20200101-000000"), "vieja")
    real_files = backup.station_files

    def with_missing(station: Station):
        yield from real_files(station)
        yield station.root / "data" / "bloqueado.db", "data/bloqueado.db"

    monkeypatch.setattr(backup, "station_files", with_missing)
    monkeypatch.setattr(commands.backup, "station_files", with_missing)

    result = _invoke(station)

    assert result.exit_code == 1
    assert "INCOMPLETO" in result.output
    assert "bloqueado.db" in result.output
    assert len(backup.archives(_folder(station))) == 2  # no se borra la antigua


def test_backup_stops_and_restarts_deeptutor(
    station: Station, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    write(station.deeptutor_cli, "")
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: True)
    monkeypatch.setattr(DeepTutor, "frontend_up", lambda self: False)
    monkeypatch.setattr(commands, "shutdown", lambda dt: calls.append("parar"))
    monkeypatch.setattr(
        commands, "launch", lambda dt, timeout: calls.append("arrancar")
    )

    result = _invoke(station)

    assert result.exit_code == 0, result.output
    assert calls == ["parar", "arrancar"]


def test_check_command(station: Station, idle: None) -> None:
    assert _invoke(station, "comprobar").exit_code == 1  # sin copias
    _invoke(station)

    result = _invoke(station, "comprobar")

    assert result.exit_code == 0, result.output
    assert "verificada" in result.output


def test_restore_command(station: Station, idle: None) -> None:
    _invoke(station)
    write(station.data_dir / "user" / "settings.json", '{"tema": "oscuro"}')

    result = _invoke(station, "restaurar", input="s\n")

    assert result.exit_code == 0, result.output
    assert "claro" in (station.data_dir / "user" / "settings.json").read_text()
    kept = list(station.root.parent.glob(f"{station.root.name}.previo-*"))
    assert len(kept) == 1
    assert "oscuro" in (kept[0] / "data" / "user" / "settings.json").read_text()
    assert not list(station.root.parent.glob(f"{station.root.name}.restaurar-*"))


def test_restore_from_other_path_needs_flag(
    station: Station, idle: None, tmp_path: Path
) -> None:
    archive = tmp_path / backup.archive_name("zip", "20261101-010000")
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(backup.MANIFEST, json.dumps({"estacion": "D:/otra"}))
        zipped.writestr("data/user/settings.json", '{"tema": "de otra"}')

    blocked = _invoke(station, "restaurar", str(archive), "--si")
    assert blocked.exit_code == 1
    assert "--nueva-ruta" in blocked.output
    assert not list(station.root.parent.glob(f"{station.root.name}.previo-*"))

    forced = _invoke(station, "restaurar", str(archive), "--si", "--nueva-ruta")
    assert forced.exit_code == 0, forced.output
    assert "de otra" in (station.data_dir / "user" / "settings.json").read_text()
