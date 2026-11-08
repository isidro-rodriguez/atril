import dataclasses
import threading

from atril.checks import Level, ok, warning
from atril.config.station import LlmConfig
from atril.errors import AtrilError
from atril.gui.model import Action, Facts, overall, service_states, tool_cards
from atril.gui.worker import Worker
from atril.ops import Reporter


class Recorder:
    """Listener que guarda los avisos en orden."""

    def __init__(self) -> None:
        self.events: list[tuple] = []

    def on_show(self, title, findings) -> None:
        self.events.append(("show", title, [f.message for f in findings]))

    def on_busy(self, text) -> None:
        self.events.append(("busy", text))

    def on_progress(self, text, total) -> None:
        self.events.append(("progress", text, total))

    def on_advance(self, amount) -> None:
        self.events.append(("advance", amount))


def _unexpected(value: object) -> None:
    raise AssertionError(f"no se esperaba: {value!r}")


def _finish(worker: Worker) -> None:
    """Espera al hilo y reparte los avisos (como haría ``after``)."""
    thread = worker._thread
    assert thread is not None
    thread.join(timeout=5)
    worker.poll()


def test_worker_delivers_events_in_order_and_result() -> None:
    listener = Recorder()
    worker = Worker(listener)
    results: list[int] = []

    def task(reporter: Reporter) -> int:
        with reporter.busy("Comprobando"):
            reporter.show([ok("bien")], "Sección")
        with reporter.progress("Comprimiendo", 10) as advance:
            advance(4)
        return 42

    assert worker.submit(task, results.append, _unexpected)
    _finish(worker)

    assert results == [42]
    assert listener.events == [
        ("busy", "Comprobando"),
        ("show", "Sección", ["bien"]),
        ("busy", None),
        ("progress", "Comprimiendo", 10),
        ("advance", 4),
        ("progress", None, 0),
    ]
    assert not worker.running


def test_worker_reports_errors_and_runs_one_job_at_a_time() -> None:
    worker = Worker(Recorder())
    gate = threading.Event()
    errors: list[Exception] = []

    def task(reporter: Reporter) -> None:
        gate.wait(5)
        raise AtrilError("no arranca")

    assert worker.submit(task, _unexpected, errors.append)
    assert not worker.submit(lambda r: None, _unexpected, _unexpected)  # ocupado
    gate.set()
    _finish(worker)

    assert [str(e) for e in errors] == ["no arranca"]
    assert not worker.running


def _facts(**changes: object) -> Facts:
    """Estación instalada y parada, con todas las herramientas."""
    base = Facts(
        deeptutor_installed=True,
        backend_up=False,
        frontend_up=False,
        ollama_installed=True,
        ollama_running=True,
        ollama_ours=False,
        ollama_models=("qwen3:8b",),
        tools={"git": True, "uv": True, "node": True, "claude": True},
        llm=LlmConfig("claude_code", "claude-code/opus"),
        ollama_required=True,
    )
    return dataclasses.replace(base, **changes)


def test_tool_cards_offer_one_action_each() -> None:
    cards = {card.key: card for card in tool_cards(_facts())}

    assert [c.key for c in tool_cards(_facts())] == [
        "deeptutor",
        "ollama",
        "git",
        "uv",
        "node",
        "asistente",
    ]
    assert cards["deeptutor"].action is Action.START
    assert cards["ollama"].action is Action.NONE  # abierto aparte: no se para
    assert cards["git"].action is Action.NONE and cards["git"].level is Level.OK
    assert cards["asistente"].name == "Claude Code"

    stopped = {
        c.key: c
        for c in tool_cards(
            _facts(
                backend_up=True,
                frontend_up=True,
                ollama_ours=True,
                tools={"git": False, "uv": True, "node": True, "claude": False},
            )
        )
    }
    assert stopped["deeptutor"].action is Action.STOP
    assert stopped["ollama"].action is Action.STOP
    assert stopped["git"].action is Action.INSTALL
    assert stopped["asistente"].action is Action.INSTALL

    missing = {
        c.key: c
        for c in tool_cards(
            _facts(
                deeptutor_installed=False,
                ollama_installed=False,
                llm=LlmConfig("ollama", "ollama/llama3:8b"),
            )
        )
    }
    assert missing["deeptutor"].action is Action.INSTALL
    assert missing["ollama"].action is Action.INSTALL
    assert missing["asistente"].action is Action.PULL


def test_overall_and_footer_states() -> None:
    assert overall(_facts())[:2] == (Level.INFO, "Parado")
    assert overall(_facts(backend_up=True, frontend_up=True))[0] is Level.OK
    assert overall(_facts(deeptutor_installed=False))[0] is Level.ERROR
    pending = _facts(pending=[warning("paginas-citas: pendiente")])
    assert overall(pending)[2] == "Paginas-citas: pendiente."
    assert service_states(_facts()) == {
        "DeepTutor": (Level.INFO, "Parado"),
        "Ollama": (Level.OK, "En marcha"),
    }


def test_source_rows_and_actions(station_dir) -> None:
    from atril.config import load_station, load_syllabus
    from atril.gui.model import (
        SyllabusData,
        actions_needed,
        filter_rows,
        source_rows,
    )
    from atril.ops import knowledge as knowledge_ops

    station = load_station(station_dir)
    syllabus = load_syllabus(station.syllabi_dir / "normativa")
    path = syllabus.source_path(syllabus.sources[0])
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.7")

    statuses, pending = knowledge_ops.status(station, syllabus)
    rows = source_rows(SyllabusData(syllabus, statuses, pending))

    first = next(row for row in rows if row.source_id == syllabus.sources[0].id)
    assert (first.state, first.level.value) == ("Por indexar", "info")
    assert any(row.state == "Sin fichero" for row in rows)
    assert actions_needed(statuses) == (True, [])
    assert filter_rows(rows, "no existe") == []
