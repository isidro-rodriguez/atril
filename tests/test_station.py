from pathlib import Path

import pytest
from support import MINIMAL_STATION, write

from atril.config import ConfigError, init_station, load_station


def test_example_station_is_valid(station_dir: Path) -> None:
    station = load_station(station_dir)

    assert station.deeptutor.patches == ("paginas-citas", "arranque-sin-ventana")
    assert station.ollama.dimension == 4096
    assert station.backup.destinations == (
        Path(r"E:\backups-atril"),
        Path(r"G:\Mi unidad\Backups\atril"),
    )
    assert station.app_dir == station_dir.resolve() / "app"


def test_defaults(tmp_path: Path) -> None:
    write(tmp_path / "atril.toml", MINIMAL_STATION)

    station = load_station(tmp_path)

    assert station.deeptutor.branch == "dev"
    assert (station.deeptutor.backend_port, station.deeptutor.frontend_port) == (
        8001,
        3782,
    )
    assert station.ollama.context == 8192
    assert station.indexing.parser == "docling"
    assert (station.indexing.chunk_size, station.indexing.chunk_overlap) == (1024, 150)
    assert (station.backup.archive_format, station.backup.keep) == ("zip", 7)
    assert (station.indexing.batch_size, station.indexing.pause_ms) == (10, 0)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("[estacion]\nraiz = 'D:/x'", "claves desconocidas: estacion"),
        ("[indexado]\nchunk = 100\nsolape = 100", "'solape' debe ser menor"),
        ("[indexado]\nchunk = true", "tipo no válido"),
    ],
)
def test_invalid_station(tmp_path: Path, extra: str, message: str) -> None:
    write(tmp_path / "atril.toml", MINIMAL_STATION + extra)

    with pytest.raises(ConfigError, match=message):
        load_station(tmp_path)


BACKUP_LINE = "destinos = ['E:\\backups-atril']"


@pytest.mark.parametrize(
    ("backup", "message"),
    [
        ("destinos = []", "al menos una carpeta"),
        ("destinos = ['copias']", "exige rutas absolutas"),
        ("destinos = ['E:/a', 'E:/a']", "destino repetido"),
        (BACKUP_LINE + "\nformato = '7z'", "'formato' debe ser"),
        (BACKUP_LINE + "\nconservar = 0", "conservar"),
        (BACKUP_LINE + "\nrepos_git = []", "claves desconocidas: repos_git"),
    ],
)
def test_invalid_backup(tmp_path: Path, backup: str, message: str) -> None:
    write(tmp_path / "atril.toml", MINIMAL_STATION.replace(BACKUP_LINE, backup))

    with pytest.raises(ConfigError, match=message):
        load_station(tmp_path)


def test_backup_folder_inside_station(tmp_path: Path) -> None:
    inside = f"destinos = ['{(tmp_path / 'data' / 'copias').as_posix()}']"
    write(tmp_path / "atril.toml", MINIMAL_STATION.replace(BACKUP_LINE, inside))

    with pytest.raises(ConfigError, match="dentro de la estación"):
        load_station(tmp_path)


def test_ports_must_differ(tmp_path: Path) -> None:
    text = MINIMAL_STATION.replace(
        "[deeptutor]", "[deeptutor]\npuertos = { backend = 8001, frontend = 8001 }"
    )
    write(tmp_path / "atril.toml", text)

    with pytest.raises(ConfigError, match="mismo puerto"):
        load_station(tmp_path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No existe"):
        load_station(tmp_path)


def test_init_station_creates_valid_template(tmp_path: Path) -> None:
    root = tmp_path / "nueva"
    init_station(root)

    assert load_station(root).ollama.dimension == 4096
    assert (root / "temarios").is_dir()
    with pytest.raises(ConfigError, match="no se sobrescribe"):
        init_station(root)


def test_unknown_patch(tmp_path: Path) -> None:
    text = MINIMAL_STATION.replace("[deeptutor]", "[deeptutor]\nparches = ['otro']")
    write(tmp_path / "atril.toml", text)

    with pytest.raises(ConfigError, match="parche desconocido: 'otro'"):
        load_station(tmp_path)


def test_install_defaults(tmp_path: Path) -> None:
    write(tmp_path / "atril.toml", MINIMAL_STATION)

    station = load_station(tmp_path)

    assert station.deeptutor.python == "3.13"
    assert station.deeptutor.packages == ()
    assert station.deeptutor.llm is None
    assert station.deeptutor.search is None
    assert station.indexing.download_models is True


def test_example_install_keys(station_dir: Path) -> None:
    dt = load_station(station_dir).deeptutor

    assert dt.llm is not None
    assert (dt.llm.provider, dt.llm.model) == ("claude_code", "claude-code/opus")
    assert dt.search == "duckduckgo"
    assert dt.packages == ("claude-agent-sdk>=0.2.174,<0.3",)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("[deeptutor.llm]\nproveedor = 'claude_code'", "'proveedor' y 'modelo'"),
        ("[indexado]\nparser = 'pdfminer'", "parser desconocido"),
    ],
)
def test_invalid_install_keys(tmp_path: Path, extra: str, message: str) -> None:
    write(tmp_path / "atril.toml", MINIMAL_STATION + extra)

    with pytest.raises(ConfigError, match=message):
        load_station(tmp_path)
