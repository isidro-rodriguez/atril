"""Casos de uso para la GUI: renombrar y borrar temarios, ajustes y Ollama."""

from pathlib import Path

import pytest

from atril import net
from atril.config import load_station, load_syllabi, load_syllabus
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.knowledge import KnowledgeApi
from atril.ollama import OllamaStatus
from atril.ops import Recorder, service
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


def test_delete_removes_folder_and_kbs(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = load_station(station_dir)
    syllabus = syllabus_ops.create(station, "Física")
    (syllabus.sources_dir / "tema.pdf").write_bytes(b"%PDF-1.7 tema")
    found = syllabus_ops.contents(syllabus)
    assert found.files >= 2 and found.knowledge_bases == ("fisica",)
    deleted: list[str] = []
    monkeypatch.setattr(DeepTutor, "installed", property(lambda self: True))
    monkeypatch.setattr(DeepTutor, "ready", lambda self: True)
    monkeypatch.setattr(KnowledgeApi, "delete_kb", lambda self, kb: deleted.append(kb))

    syllabus_ops.delete(station, syllabus, Recorder())

    assert deleted == ["fisica"]
    assert not syllabus.root.exists()
    syllabi, _ = load_syllabi(station.syllabi_dir)
    assert [s.id for s in syllabi] == ["normativa"]


def test_delete_keeps_folder_if_a_kb_fails(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = load_station(station_dir)
    syllabus = syllabus_ops.create(station, "Física")
    monkeypatch.setattr(DeepTutor, "installed", property(lambda self: True))
    monkeypatch.setattr(DeepTutor, "ready", lambda self: True)

    def refuse(self: KnowledgeApi, kb: str) -> None:
        raise net.HttpError(500, "fallo")

    monkeypatch.setattr(KnowledgeApi, "delete_kb", refuse)
    with pytest.raises(AtrilError, match="no ha borrado"):
        syllabus_ops.delete(station, syllabus, Recorder())
    assert syllabus.root.is_dir()


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
        settings_ops.update(updated, {"deeptutor": {"inventada": 1}})
    assert path.read_text(encoding="utf-8") == before


def test_settings_edit_nested_tables_and_remove_optional(station_dir: Path) -> None:
    station = load_station(station_dir)
    path = station_dir / "atril.toml"

    updated = settings_ops.update(
        station,
        {
            "deeptutor.puertos": {"backend": 8101},
            "deeptutor.llm": None,
            "indexado": {"hilos": None},
        },
    )

    assert updated.deeptutor.backend_port == 8101
    assert updated.deeptutor.llm is None
    text = path.read_text(encoding="utf-8")
    assert "backend = 8101" in text and "[deeptutor.llm]" not in text
    assert "# por defecto" in text  # conserva comentarios
    assert settings_ops.effects(station, updated) == [settings_ops.Effect.APPLY]

    no_ollama = settings_ops.update(updated, {"ollama": None})
    assert no_ollama.ollama is None
    with pytest.raises(AtrilError, match="no se puede quitar"):
        settings_ops.update(no_ollama, {"backup": None})


def test_settings_effects(station_dir: Path) -> None:
    station = load_station(station_dir)
    effect = settings_ops.Effect

    pace = settings_ops.update(station, {"indexado": {"lote_embedding": 2}})
    assert settings_ops.effects(station, pace) == []
    vectors = settings_ops.update(pace, {"ollama": {"dimension": 1024}})
    assert settings_ops.effects(pace, vectors) == [effect.APPLY, effect.REINDEX]
    branch = settings_ops.update(vectors, {"deeptutor": {"rama": "main"}})
    assert settings_ops.effects(vectors, branch) == [effect.REINSTALL]


def test_only_the_ollama_started_by_atril_is_stopped(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    station = load_station(station_dir)
    monkeypatch.setattr(service.ollama, "launch", lambda: 4242)
    monkeypatch.setattr(service.processes, "started_at", lambda pid: 100.0)
    monkeypatch.setattr(
        service.ollama, "get_status", lambda url: OllamaStatus(running=True)
    )
    killed: list[int] = []
    monkeypatch.setattr(service.processes, "kill_tree", killed.append)

    service.start_ollama(station, Recorder())
    assert service.ollama_owner(station) == 4242

    monkeypatch.setattr(service.processes, "started_at", lambda pid: 999.0)
    assert service.ollama_owner(station) is None  # PID reutilizado: no es el nuestro
    with pytest.raises(AtrilError, match="no lo abrió atril"):
        service.stop_ollama(station, Recorder())
    assert killed == []

    monkeypatch.setattr(service.processes, "started_at", lambda pid: 100.0)
    service.stop_ollama(station, Recorder())
    assert killed == [4242]
    assert service.ollama_owner(station) is None


@pytest.mark.parametrize(("installed", "ours"), [(True, True), (False, False)])
def test_shutdown_stops_deeptutor_and_only_our_ollama(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch, installed: bool, ours: bool
) -> None:
    station = load_station(station_dir)
    calls: list[str] = []
    monkeypatch.setattr(DeepTutor, "installed", property(lambda self: installed))
    monkeypatch.setattr(service, "stop", lambda dt, reporter: calls.append("dt"))
    monkeypatch.setattr(service, "ollama_owner", lambda st: 4242 if ours else None)
    monkeypatch.setattr(
        service, "stop_ollama", lambda st, reporter: calls.append("ollama")
    )

    service.shutdown(station, Recorder())

    assert calls == (["dt", "ollama"] if installed else [])


def test_active_assistant_reads_deeptutor_catalog_without_the_key(
    station_dir: Path,
) -> None:
    import json

    from atril.deeptutor import MODEL_CATALOG, Assistant, active_assistant

    station = load_station(station_dir)
    assert active_assistant(station) is None  # sin catálogo
    catalog = {
        "connections": [{"id": "c1", "api_key": "secreta"}],
        "services": {
            "llm": {
                "active_profile_id": "p2",
                "active_model_id": "m2",
                "profiles": [
                    {"id": "p1", "binding": "claude_code", "api_key": "", "models": []},
                    {
                        "id": "p2",
                        "binding": "gemini",
                        "api_key": "",
                        "provider_ref": {"connection_id": "c1"},
                        "models": [{"id": "m2", "model": "gemini-2.5-pro"}],
                    },
                ],
            }
        },
    }
    path = station.root / MODEL_CATALOG
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(catalog), encoding="utf-8")

    assert active_assistant(station) == Assistant("gemini", "gemini-2.5-pro", True)
