import json
import os
import sys
import time
from pathlib import Path

import pytest
from support import write

from atril import knowledge, net
from atril.config import StateFileError, load_station, load_syllabus
from atril.config.syllabus import Syllabus
from atril.knowledge import (
    IndexedSource,
    Indexer,
    KbRun,
    KnowledgeApi,
    Ledger,
    PlanItem,
    PlanState,
    content_digest,
    ledger_path,
    plan,
)


@pytest.fixture
def syllabus(station_dir: Path) -> Syllabus:
    loaded = load_syllabus(station_dir / "temarios" / "normativa")
    for source in loaded.sources:
        path = loaded.source_path(source)
        assert path is not None
        write(path, f"%PDF {source.id}")
    return loaded


def _states(items: list[PlanItem]) -> dict[str, PlanState]:
    return {item.source_id: item.state for item in items}


def test_plan_new_indexed_changed_removed_missing(syllabus: Syllabus) -> None:
    kb = syllabus.knowledge_bases[0]
    ledger = Ledger(ledger_path(syllabus))
    assert _states(plan(syllabus, kb, ledger)) == {
        "cte-db-si": PlanState.NEW,
        "loe": PlanState.NEW,
    }

    cte = syllabus.sources[0]
    cte_path = syllabus.source_path(cte)
    assert cte_path is not None
    entry = ledger.kb(kb.id)
    entry.sources["cte-db-si"] = IndexedSource(
        "DBSI.pdf", content_digest(cte, cte_path), "t"
    )
    entry.sources["loe"] = IndexedSource("LOE.pdf", "hash-anterior", "t")
    entry.sources["retirada"] = IndexedSource("viejo.pdf", "h", "t")
    assert _states(plan(syllabus, kb, ledger))["cte-db-si"] is PlanState.INDEXED

    cte_path.unlink()
    assert _states(plan(syllabus, kb, ledger)) == {
        "cte-db-si": PlanState.MISSING,
        "loe": PlanState.CHANGED,
        "retirada": PlanState.REMOVED,
    }


def test_ledger_roundtrip(syllabus: Syllabus) -> None:
    ledger = Ledger(ledger_path(syllabus))
    ledger.kb("kb-b").sources["x"] = IndexedSource("x.pdf", "h", "t", 1.5)
    ledger.kb("kb-a").pending_reindex = True
    ledger.save()

    reloaded = Ledger(ledger_path(syllabus))
    assert reloaded.kbs["kb-a"].pending_reindex is True
    assert reloaded.kbs["kb-b"].sources["x"] == IndexedSource("x.pdf", "h", "t", 1.5)
    text = ledger_path(syllabus).read_text(encoding="utf-8")
    assert text.index("kb-a") < text.index("kb-b")


@pytest.mark.parametrize("text", ["[]x", '{"kb": {"a": {"fuentes": {"x": 1}}}}'])
def test_damaged_ledger_raises(syllabus: Syllabus, text: str) -> None:
    write(ledger_path(syllabus), text)

    with pytest.raises(StateFileError):
        Ledger(ledger_path(syllabus))


def test_markdown_digest_tracks_content(tmp_path: Path) -> None:
    root = tmp_path / "t"
    write(
        root / "temario.toml",
        '[temario]\nnombre = "T"\n[[kb]]\nid = "kb"\nvinculante = false\n'
        'fuentes = ["*"]\n[[fuente]]\nid = "notas"\ntipo = "markdown"\n'
        'carpeta = "notas"\n',
    )
    syllabus = load_syllabus(root)
    source = syllabus.sources[0]
    folder = syllabus.source_path(source)
    assert folder is not None
    write(folder / "a.md", "uno")
    first = content_digest(source, folder)
    write(folder / "a.md", "dos")

    assert content_digest(source, folder) != first


def test_kb_run_state_and_description(tmp_path: Path) -> None:
    now = time.time()
    data = {
        "task_id": "t1",
        "state": "running",
        "pid": 999_999_999,
        "phase": "embedding",
        "phase_current": 3,
        "phase_total": 10,
        "last_activity_at": now - 42,
        "documents": {"a.pdf": {"status": "completed"}, "b.pdf": {"status": "running"}},
    }
    (tmp_path / ".indexing-run.json").write_text(json.dumps(data))

    run = KbRun.load(tmp_path)
    assert run is not None
    assert run.state == "interrupted"  # el proceso dueño ya no existe
    assert run.describe(now) == "embedding · docs 1/2 · 3/10 · actividad hace 42 s"
    assert KbRun.load(tmp_path / "nada") is None


def test_command_creates_then_adds(station_dir: Path, syllabus: Syllabus) -> None:
    station = load_station(station_dir)
    indexer = Indexer(station, env={})
    kb = syllabus.knowledge_bases[0]
    cte = plan(syllabus, kb, Ledger(ledger_path(syllabus)))[0]

    assert indexer.command(kb.id, cte)[-4:-1] == ["create", kb.id, "--doc"]
    write(station.kb_dir(kb.id) / "metadata.json", "{}")
    assert indexer.command(kb.id, cte)[-4:-1] == ["add", kb.id, "--doc"]


@pytest.fixture
def fast_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge, "POLL_SECONDS", 0.01)


def _run_with(monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    """Indexer.command ejecuta ``script`` con Python en lugar de deeptutor."""
    monkeypatch.setattr(
        Indexer, "command", lambda self, kb_id, item: [sys.executable, "-c", script]
    )


def test_add_detects_new_completed_run_whatever_the_name(
    station_dir: Path,
    syllabus: Syllabus,
    monkeypatch: pytest.MonkeyPatch,
    fast_poll: None,
) -> None:
    station = load_station(station_dir)
    kb = syllabus.knowledge_bases[0]
    run_file = station.kb_dir(kb.id) / ".indexing-run.json"
    write(run_file, json.dumps({"task_id": "viejo", "state": "completed"}))
    # DeepTutor guarda la versión nueva como "DBSI (2).pdf" si ya hay un DBSI.pdf.
    new_run = {
        "task_id": "nuevo",
        "state": "completed",
        "documents": {"DBSI (2).pdf": {}},
    }
    script = (
        "import json, pathlib, time; time.sleep(0.05); "
        f"pathlib.Path({str(run_file)!r}).write_text({json.dumps(json.dumps(new_run))})"
    )
    _run_with(monkeypatch, script)
    item = plan(syllabus, kb, Ledger(ledger_path(syllabus)))[0]
    ticks: list[float] = []

    result = Indexer(station, env={}).add(kb.id, item, lambda run, t: ticks.append(t))

    assert result.ok
    assert ticks


def test_add_accepts_already_indexed_and_reports_failures(
    station_dir: Path,
    syllabus: Syllabus,
    monkeypatch: pytest.MonkeyPatch,
    fast_poll: None,
) -> None:
    station = load_station(station_dir)
    kb = syllabus.knowledge_bases[0]
    item = plan(syllabus, kb, Ledger(ledger_path(syllabus)))[0]
    indexer = Indexer(station, env={})

    _run_with(monkeypatch, "print('Skipped (content already indexed): DBSI.pdf')")
    duplicate = indexer.add(kb.id, item)
    assert duplicate.ok
    assert "ya estaba" in duplicate.detail

    _run_with(monkeypatch, "import sys; print('boom'); sys.exit(3)")
    failed = indexer.add(kb.id, item)
    assert not failed.ok
    assert "código de salida 3" in failed.detail
    assert failed.log is not None
    assert "boom" in failed.log.read_text(encoding="utf-8")


def test_remote_source_cannot_create_kb(station_dir: Path, tmp_path: Path) -> None:
    root = load_station(station_dir).syllabi_dir / "remoto"
    write(
        root / "temario.toml",
        '[temario]\nnombre = "R"\n[[kb]]\nid = "kb-remota"\nvinculante = false\n'
        'fuentes = ["*"]\n[[fuente]]\nid = "doc"\ntipo = "web"\nurl = "https://boe.es"\n',
    )
    syllabus = load_syllabus(root)
    kb = syllabus.knowledge_bases[0]
    item = plan(syllabus, kb, Ledger(ledger_path(syllabus)))[0]

    result = Indexer(load_station(station_dir), env={}).add(kb.id, item)

    assert not result.ok
    assert "fuente remota" in result.detail


def test_knowledge_api(station_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake(
        url: str, method: str = "GET", form: dict | None = None, **kw: object
    ) -> dict:
        calls.append((method, url, form))
        if url.endswith("/reindex"):
            raise net.HttpError(404, "Knowledge base not found")
        return {"was_indexed": True, "task_id": "t"}

    monkeypatch.setattr(net, "request_json", fake)
    api = KnowledgeApi(load_station(station_dir))

    assert api.delete_file("kb-a", "a (2).pdf") is True
    assert api.reindex("kb-a", '{"model_id": "m"}')["task_id"] == "t"
    base = "http://127.0.0.1:8001/api/knowledge-bases/kb-a"
    assert calls[0][:2] == ("DELETE", f"{base}/files/a%20%282%29.pdf")
    assert calls[2][1] == f"{base}/reindex?resource_library=true"
    assert calls[2][2] == {"embedding_model": '{"model_id": "m"}'}


def test_add_limits_threads_and_lowers_priority(
    station_dir: Path,
    syllabus: Syllabus,
    monkeypatch: pytest.MonkeyPatch,
    fast_poll: None,
) -> None:
    text = (station_dir / "atril.toml").read_text(encoding="utf-8")
    (station_dir / "atril.toml").write_text(
        text.replace("hilos = 0", "hilos = 3"), encoding="utf-8"
    )
    station = load_station(station_dir)
    kb = syllabus.knowledge_bases[0]
    item = plan(syllabus, kb, Ledger(ledger_path(syllabus)))[0]
    lowered: list[int] = []
    monkeypatch.setattr(knowledge, "lower_priority", lowered.append)
    _run_with(
        monkeypatch,
        "import os; print('Skipped (content already indexed):', "
        "os.environ['OMP_NUM_THREADS'], os.environ['MKL_NUM_THREADS'])",
    )

    result = Indexer(station, env={"PATH": os.environ.get("PATH", "")}).add(kb.id, item)

    assert result.ok
    assert len(lowered) == 1
    log = sorted(station.logs_dir.glob("indexado-*.log"))[-1]
    assert "3 3" in log.read_text(encoding="utf-8")


def test_add_ignores_stale_run_and_explains_reindex_required(
    station_dir: Path,
    syllabus: Syllabus,
    monkeypatch: pytest.MonkeyPatch,
    fast_poll: None,
) -> None:
    station = load_station(station_dir)
    kb = syllabus.knowledge_bases[0]
    # Run de un indexado anterior que se quedó colgado.
    stale = {"task_id": "viejo", "state": "failed", "error": "no progress for 35263s"}
    write(station.kb_dir(kb.id) / ".indexing-run.json", json.dumps(stale))
    _run_with(
        monkeypatch,
        "import sys, time; time.sleep(0.05); print('Document upload failed: Knowledge "
        "base has no ready llamaindex index; reindex required'); sys.exit(1)",
    )
    item = plan(syllabus, kb, Ledger(ledger_path(syllabus)))[0]
    seen: list[object] = []

    result = Indexer(station, env={}).add(kb.id, item, lambda run, t: seen.append(run))

    assert not result.ok
    assert f"atril kb reindexar {kb.id}" in result.detail
    assert "35263" not in result.detail
    assert seen and all(run is None for run in seen)


@pytest.mark.parametrize(
    "entry",
    [
        {"reindexar": "false", "fuentes": {}},
        {"reindexar": False},
        {"reindexar": False, "fuentes": {"x": {"file": "a.pdf", "sha256": "h"}}},
    ],
)
def test_ledger_is_strict(syllabus: Syllabus, entry: dict) -> None:
    write(ledger_path(syllabus), json.dumps({"version": 1, "kb": {"cte": entry}}))

    with pytest.raises(StateFileError):
        Ledger(ledger_path(syllabus))


def test_file_digest_is_remembered_until_the_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "grande.pdf"
    big.write_bytes(b"%PDF" + b"x" * knowledge.CACHED_SIZE)
    calls: list[Path] = []
    real = knowledge.get_file_hash

    def counting(path: Path) -> str:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(knowledge, "get_file_hash", counting)
    first = knowledge.file_digest(big)
    assert knowledge.file_digest(big) == first
    assert len(calls) == 1  # la segunda vez no se relee

    big.write_bytes(b"%PDF" + b"y" * (knowledge.CACHED_SIZE + 1))
    assert knowledge.file_digest(big) != first
    assert len(calls) == 2
