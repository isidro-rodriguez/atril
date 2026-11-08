"""Casos de uso para la GUI: renombrar y eliminar temarios, recientes y ajustes."""

import os
from pathlib import Path

import pytest

from atril.config import load_station, load_syllabi, load_syllabus
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.knowledge import KnowledgeApi
from atril.ops import Recorder
from atril.ops import settings as settings_ops
from atril.ops import syllabus as syllabus_ops


def test_rename_keeps_id_and_comments(station_dir: Path) -> None:
    root = station_dir / "temarios" / "normativa"
    renamed = syllabus_ops.rename(load_syllabus(root), "Normativa técnica")

    assert (renamed.id, renamed.name) == ("normativa", "Normativa técnica")
    text = (root / "temario.toml").read_text(encoding="utf-8")
    assert "# Cada fuente pertenece a una sola KB" in text
    with pytest.raises(AtrilError, match="nombre"):
        syllabus_ops.rename(renamed, "  ")


def test_delete_moves_to_trash_and_keeps_kbs(station_dir: Path) -> None:
    station = load_station(station_dir)
    syllabus = syllabus_ops.create(station, "Física")

    target = syllabus_ops.delete(station, syllabus, Recorder(), delete_kbs=False)

    assert target.parent == station.syllabi_dir / ".papelera"
    assert (target / "temario.toml").is_file()
    syllabi, warnings = load_syllabi(station.syllabi_dir)
    assert [s.id for s in syllabi] == ["normativa"]  # la papelera no es un temario
    assert not any(".papelera" in w for w in warnings)


def test_delete_can_remove_kbs_from_deeptutor(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = load_station(station_dir)
    syllabus = syllabus_ops.create(station, "Física")
    deleted: list[str] = []
    monkeypatch.setattr(DeepTutor, "installed", property(lambda self: True))
    monkeypatch.setattr(DeepTutor, "ready", lambda self: True)
    monkeypatch.setattr(KnowledgeApi, "delete_kb", lambda self, kb: deleted.append(kb))

    syllabus_ops.delete(station, syllabus, Recorder(), delete_kbs=True)

    assert deleted == ["fisica"]


def test_recent_orders_by_modification(station_dir: Path) -> None:
    station = load_station(station_dir)
    older = syllabus_ops.create(station, "Antiguo")
    newer = syllabus_ops.create(station, "Nuevo")
    for path in (older.root / "temario.toml", older.sources_dir):
        os.utime(path, (1_000_000, 1_000_000))

    order = [s.id for s, _ in syllabus_ops.recent([older, newer])]

    assert order == ["nuevo", "antiguo"]


def test_settings_update_validates_before_writing(station_dir: Path) -> None:
    station = load_station(station_dir)
    path = station_dir / "atril.toml"

    updated = settings_ops.update(station, {"backup": {"conservar": 12}})
    assert updated.backup.keep == 12
    assert "conservar = 12" in path.read_text(encoding="utf-8")

    before = path.read_text(encoding="utf-8")
    inside = str(station_dir / "copias")
    with pytest.raises(AtrilError, match="dentro de la estación"):
        settings_ops.update(updated, {"backup": {"destinos": [inside]}})
    with pytest.raises(AtrilError, match="no se cambia"):
        settings_ops.update(updated, {"deeptutor": {"rama": "main"}})
    assert path.read_text(encoding="utf-8") == before
