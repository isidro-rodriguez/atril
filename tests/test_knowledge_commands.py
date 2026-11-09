import json
import os
import time
from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import ollama
from atril.checks import ok
from atril.commands import knowledge as commands
from atril.config import load_station, load_syllabus
from atril.deeptutor import DeepTutor
from atril.install import Installer
from atril.knowledge import (
    AddResult,
    IndexedSource,
    Indexer,
    KnowledgeApi,
    Ledger,
    content_digest,
    ledger_path,
)
from atril.lock import station_lock
from atril.main import app
from atril.ollama import OllamaStatus
from atril.ops import knowledge as knowledge_ops
from atril.ops import service

runner = CliRunner()


@pytest.fixture
def station(station_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Estación con fuentes en disco, DeepTutor instalado y servicios simulados."""
    loaded = load_station(station_dir)
    write(loaded.deeptutor_cli, "")
    syllabus = load_syllabus(loaded.syllabi_dir / "normativa")
    for source in syllabus.sources:
        path = syllabus.source_path(source)
        assert path is not None
        write(path, f"%PDF {source.id}")

    clock = [0.0]

    def fake_sleep(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(time, "sleep", fake_sleep)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        ollama,
        "get_status",
        lambda url: OllamaStatus(True, "0.12.0", ("qwen3-embedding:8b",)),
    )
    monkeypatch.setattr(ollama, "probe_embedding", lambda config: [ok("embed")])
    monkeypatch.setattr(
        Installer, "runtime_settings", lambda self: [ok("ajustes aplicados")]
    )
    return station_dir


def _invoke(station: Path, *args: str):
    return runner.invoke(app, [*args], env={"ATRIL_ESTACION": str(station)})


def _record_adds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    added: list[str] = []

    def fake_add(self: Indexer, kb_id: str, item, tick=None) -> AddResult:
        added.append(f"{kb_id}:{item.file}")
        write(self.station.kb_dir(kb_id) / "metadata.json", "{}")
        return AddResult(True, 0.5)

    monkeypatch.setattr(Indexer, "add", fake_add)
    return added


def _ledger(station: Path) -> Ledger:
    return Ledger(ledger_path(load_syllabus(station / "temarios" / "normativa")))


def test_index_adds_new_sources_and_is_idempotent(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = _record_adds(monkeypatch)

    result = _invoke(station, "kb", "indexar", "normativa")

    assert result.exit_code == 0, result.output
    assert added == [
        "norm-edificacion-cte:DBSI.pdf",
        "norm-edificacion-cte:LOE.pdf",
        "norm-edificacion-cte-guias:guia-db-si.pdf",
    ]
    assert set(_ledger(station).kb("norm-edificacion-cte").sources) == {
        "cte-db-si",
        "loe",
    }

    added.clear()
    again = _invoke(station, "kb", "indexar", "normativa")
    assert again.exit_code == 0
    assert added == []
    assert "Nada que indexar" in again.output


def test_index_one_kb_and_unknown_kb(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = _record_adds(monkeypatch)

    result = _invoke(
        station, "kb", "indexar", "normativa", "norm-edificacion-cte-guias"
    )
    assert result.exit_code == 0, result.output
    assert added == ["norm-edificacion-cte-guias:guia-db-si.pdf"]

    result = _invoke(station, "kb", "indexar", "normativa", "otra")
    assert result.exit_code == 1
    assert "no tiene la KB 'otra'" in result.output


def test_index_skips_changed_and_asks_for_reindex(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = _record_adds(monkeypatch)
    _invoke(station, "kb", "indexar", "normativa")
    syllabus = load_syllabus(station / "temarios" / "normativa")
    path = syllabus.source_path(syllabus.sources[0])
    assert path is not None
    write(path, "%PDF nueva versión")
    added.clear()

    result = _invoke(station, "kb", "indexar", "normativa")

    assert result.exit_code == 0, result.output
    assert added == []
    assert "cambiada" in result.output
    assert "hay que reindexarla" in result.output


def test_index_failure_shows_log(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = load_station(station).logs_dir / "indexado.log"
    write(log, "Traceback\nCUDA error: out of memory\n")
    monkeypatch.setattr(
        Indexer,
        "add",
        lambda self, kb_id, item, tick=None: AddResult(False, 1.0, "fallo", log),
    )

    result = _invoke(station, "kb", "indexar", "normativa")

    assert result.exit_code == 1
    assert "CUDA error" in result.output
    assert "Vuelve a indexar" in result.output


def test_index_stops_when_embedding_fails(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.checks import error

    monkeypatch.setattr(ollama, "probe_embedding", lambda config: [error("CUDA error")])
    added = _record_adds(monkeypatch)

    result = _invoke(station, "kb", "indexar", "normativa")

    assert result.exit_code == 1
    assert added == []


@pytest.fixture
def reindex_env(station: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """KB indexada con DBSI y LOE, DT en marcha y API/run simulados."""
    syllabus = load_syllabus(station / "temarios" / "normativa")
    loaded = load_station(station)
    kb_dir = loaded.kb_dir("norm-edificacion-cte")
    write(kb_dir / "metadata.json", "{}")
    write(
        kb_dir / ".indexing-run.json",
        json.dumps({"task_id": "t0", "state": "completed"}),
    )
    ledger = Ledger(ledger_path(syllabus))
    cte, loe = syllabus.sources[0], syllabus.sources[1]
    for source in (cte, loe):
        path = syllabus.source_path(source)
        assert path is not None
        ledger.kb("norm-edificacion-cte").sources[source.id] = IndexedSource(
            path.name, content_digest(source, path), "t"
        )
    ledger.kb("norm-edificacion-cte").sources["retirada"] = IndexedSource(
        "viejo.pdf", "h", "t"
    )
    ledger.save()

    calls: dict[str, list] = {"deleted": [], "reindexed": [], "lifecycle": []}
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: True)
    monkeypatch.setattr(
        knowledge_ops, "embedding_selection", lambda station, env: '{"m": 1}'
    )

    def fake_delete(self: KnowledgeApi, kb_id: str, filename: str) -> bool:
        calls["deleted"].append(filename)
        return True

    def fake_reindex(self: KnowledgeApi, kb_id: str, selection: str) -> dict:
        calls["reindexed"].append(selection)
        write(
            kb_dir / ".indexing-run.json",
            json.dumps({"task_id": "t1", "state": "completed"}),
        )
        return {"task_id": "t1"}

    monkeypatch.setattr(KnowledgeApi, "delete_file", fake_delete)
    monkeypatch.setattr(KnowledgeApi, "reindex", fake_reindex)
    monkeypatch.setattr(
        service, "stop", lambda dt, reporter: calls["lifecycle"].append("parar")
    )
    monkeypatch.setattr(
        service,
        "start",
        lambda dt, reporter, timeout: calls["lifecycle"].append("arrancar"),
    )
    calls["added"] = _record_adds(monkeypatch)
    return calls


def test_reindex_replaces_changed_and_purges_removed(
    station: Path, reindex_env: dict[str, list]
) -> None:
    syllabus = load_syllabus(station / "temarios" / "normativa")
    loe_path = syllabus.source_path(syllabus.sources[1])
    assert loe_path is not None
    write(loe_path, "%PDF LOE modificada")

    result = _invoke(station, "kb", "reindexar", "norm-edificacion-cte")

    assert result.exit_code == 0, result.output
    assert reindex_env["deleted"] == ["viejo.pdf", "LOE.pdf"]
    assert reindex_env["added"] == ["norm-edificacion-cte:LOE.pdf"]
    assert reindex_env["reindexed"] == ['{"m": 1}']
    entry = _ledger(station).kb("norm-edificacion-cte")
    assert set(entry.sources) == {"cte-db-si", "loe"}
    assert entry.sources["loe"].sha256 == content_digest(syllabus.sources[1], loe_path)
    assert entry.pending_reindex is False


def test_reindex_restarts_stuck_worker(
    station: Path, reindex_env: dict[str, list]
) -> None:
    kb_dir = load_station(station).kb_dir("norm-edificacion-cte")
    write(
        kb_dir / ".indexing-run.json", json.dumps({"task_id": "t0", "state": "failed"})
    )

    result = _invoke(station, "kb", "reindexar", "norm-edificacion-cte")

    assert result.exit_code == 0, result.output
    assert reindex_env["lifecycle"] == ["parar", "arrancar"]
    assert "liberar el worker" in result.output


def test_reindex_reports_failed_run(
    station: Path, reindex_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    kb_dir = load_station(station).kb_dir("norm-edificacion-cte")

    def failing(self: KnowledgeApi, kb_id: str, selection: str) -> dict:
        run = {
            "task_id": "t1",
            "state": "failed",
            "error": "http://localhost:11434 timeout",
        }
        write(kb_dir / ".indexing-run.json", json.dumps(run))
        return {"task_id": "t1"}

    monkeypatch.setattr(KnowledgeApi, "reindex", failing)

    result = _invoke(station, "kb", "reindexar", "norm-edificacion-cte")

    assert result.exit_code == 1
    assert "failed" in result.output
    assert "GPU" in result.output
    assert (
        _ledger(station).kb("norm-edificacion-cte").sources.get("retirada") is not None
    )


def test_reindex_unknown_or_missing_kb(station: Path) -> None:
    result = _invoke(station, "kb", "reindexar", "nada")
    assert result.exit_code == 1
    assert "no existe la KB 'nada'" in result.output

    result = _invoke(station, "kb", "reindexar", "norm-edificacion-cte")
    assert result.exit_code == 1
    assert "aún no existe" in result.output


@pytest.fixture
def wide(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consola de 120 columnas, como el terminal de destino."""
    monkeypatch.setattr(commands.console, "width", 120)


def test_status_shows_counts_and_changes_nothing(
    station: Path, monkeypatch: pytest.MonkeyPatch, wide: None
) -> None:
    _record_adds(monkeypatch)
    _invoke(station, "kb", "indexar", "normativa", "norm-edificacion-cte")
    ledger_file = ledger_path(load_syllabus(station / "temarios" / "normativa"))
    before = ledger_file.read_bytes()
    monkeypatch.setattr(Indexer, "add", lambda *a, **k: pytest.fail("no indexa"))

    result = _invoke(station, "kb", "estado")

    assert result.exit_code == 0, result.output
    rows = {
        line.split("│")[1].strip(): [c.strip() for c in line.split("│")[2:-1]]
        for line in result.output.splitlines()
        if line.startswith("│")
    }
    assert rows["norm-edificacion-cte"][:6] == ["2", "2", "0", "0", "0", "0"]
    assert rows["norm-edificacion-cte-guias"][:3] == ["1", "0", "1"]
    assert rows["norm-edificacion-cte-guias"][6] == "sin crear"
    assert "por indexar guia-cte-si" in result.output
    assert ledger_file.read_bytes() == before


def test_status_reports_running_run(station: Path, wide: None) -> None:
    kb_dir = load_station(station).kb_dir("norm-edificacion-cte")
    write(
        kb_dir / ".indexing-run.json",
        json.dumps({"task_id": "t1", "state": "running", "phase": "embedding"}),
    )

    result = _invoke(station, "kb", "estado", "normativa", "norm-edificacion-cte")

    assert result.exit_code == 0, result.output
    # El proceso dueño no existe: un run "running" huérfano cuenta como interrumpido.
    assert "interrumpido" in result.output


def test_index_cancel_stops_in_tick_and_keeps_source_pending(
    station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from atril.errors import CancelledError
    from atril.ops import Recorder

    cancel = threading.Event()

    def add(self, kb_id, item, tick=None):
        cancel.set()  # el usuario pulsa «Cancelar» mientras se indexa
        assert tick is not None
        tick(None, 30.0)
        pytest.fail("el tick debía cancelar")

    monkeypatch.setattr(Indexer, "add", add)
    syllabus = load_syllabus(station / "temarios" / "normativa")

    with pytest.raises(CancelledError, match="continúa por ella"):
        knowledge_ops.index(load_station(station), syllabus, Recorder(), cancel=cancel)

    ledger = Ledger(ledger_path(syllabus))
    assert not ledger.kb("norm-edificacion-cte").sources  # nada se da por indexado
    with station_lock(load_station(station), "comprobar"):
        pass  # liberado


def test_download_cancel_between_sources(station: Path) -> None:
    import threading

    from atril.errors import CancelledError
    from atril.ops import Recorder
    from atril.ops import sources as source_ops

    cancel = threading.Event()
    cancel.set()
    syllabus = load_syllabus(station / "temarios" / "normativa")

    with pytest.raises(CancelledError):
        source_ops.download(syllabus, Recorder(), cancel=cancel)


def test_reindex_waits_for_its_own_task_and_restores_stopped_deeptutor(
    station: Path, reindex_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresión: el run de un añadido (otra tarea) no da el reindexado por hecho."""
    kb_dir = load_station(station).kb_dir("norm-edificacion-cte")
    syllabus = load_syllabus(station / "temarios" / "normativa")
    loe_path = syllabus.source_path(syllabus.sources[1])
    assert loe_path is not None
    write(loe_path, "%PDF LOE modificada")

    def add_with_run(self: Indexer, kb_id: str, item, tick=None) -> AddResult:
        # Como `deeptutor kb add`: deja su propio run, ya completado.
        run = {"task_id": "anadido", "state": "completed"}
        write(kb_dir / ".indexing-run.json", json.dumps(run))
        return AddResult(True, 0.5)

    def reindex_later(self: KnowledgeApi, kb_id: str, selection: str) -> dict:
        return {"task_id": "t1"}  # DeepTutor escribe su run un poco después

    states = iter(["running", "running", "completed"])
    written: list[str] = []

    def sleep(seconds: float) -> None:
        state = next(states, "completed")
        run = {"task_id": "t1", "state": state, "pid": os.getpid()}
        write(kb_dir / ".indexing-run.json", json.dumps(run))
        written.append(state)

    monkeypatch.setattr(Indexer, "add", add_with_run)
    monkeypatch.setattr(KnowledgeApi, "reindex", reindex_later)
    monkeypatch.setattr(DeepTutor, "backend_up", lambda self: False)
    monkeypatch.setattr(time, "sleep", sleep)

    result = _invoke(station, "kb", "reindexar", "norm-edificacion-cte")

    assert result.exit_code == 0, result.output
    assert written[-1] == "completed"  # siguió el run t1 hasta el final
    assert len(written) >= 3
    # DeepTutor estaba parado: se arranca para reindexar y se para al terminar.
    assert reindex_env["lifecycle"] == ["arrancar", "parar"]


@pytest.mark.parametrize(("action", "needs"), [("rebuild", True), ("upload", False)])
def test_unfinished_rebuild_asks_for_reindex(
    station: Path, action: str, needs: bool
) -> None:
    """Regresión: un reindexado interrumpido sigue pidiendo reindexar.

    Aunque el registro propio lo diera por hecho (atril lo anotaba al lanzarlo).
    """
    loaded = load_station(station)
    kb_dir = loaded.kb_dir("norm-edificacion-cte")
    write(kb_dir / "metadata.json", "{}")
    run = {"task_id": "t1", "action": action, "state": "interrupted"}
    write(kb_dir / ".indexing-run.json", json.dumps(run))
    syllabus = load_syllabus(station / "temarios" / "normativa")

    statuses, findings = knowledge_ops.status(loaded, syllabus, "norm-edificacion-cte")

    assert statuses[0].needs_reindex is needs
    assert any("reindexa para completarlo" in f.message for f in findings) is needs
