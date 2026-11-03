from pathlib import Path

import pytest
from support import MINIMAL_STATION, write

from atril.config import ConfigError, find_station, load_station


def test_example_station_is_valid(station_dir: Path) -> None:
    station = load_station(station_dir)

    assert station.deeptutor.patches == ("paginas-citas",)
    assert station.ollama.dimension == 4096
    assert [t.name for t in station.backup.targets] == ["disco", "drive"]
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
    assert station.backup.retention.daily == 7


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


def test_ports_must_differ(tmp_path: Path) -> None:
    text = MINIMAL_STATION.replace(
        "[deeptutor]", "[deeptutor]\npuertos = { backend = 8001, frontend = 8001 }"
    )
    write(tmp_path / "atril.toml", text)

    with pytest.raises(ConfigError, match="mismo puerto"):
        load_station(tmp_path)


def test_backup_needs_a_target(tmp_path: Path) -> None:
    text = MINIMAL_STATION.replace(
        "[backup.destinos.disco]\nrepo = 'E:\\restic-atril'", "[backup.destinos]"
    )
    write(tmp_path / "atril.toml", text)

    with pytest.raises(ConfigError, match="al menos un destino"):
        load_station(tmp_path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No existe"):
        load_station(tmp_path)


def test_find_station_walks_up(tmp_path: Path) -> None:
    write(tmp_path / "atril.toml", MINIMAL_STATION)
    nested = tmp_path / "temarios" / "normativa"
    nested.mkdir(parents=True)

    assert find_station(nested) == tmp_path.resolve()


def test_find_station_fails_outside(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="--estacion"):
        find_station(tmp_path)
