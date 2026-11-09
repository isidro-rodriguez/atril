import dataclasses
import threading

import pytest

from atril.checks import Level, ok, warning
from atril.deeptutor import Assistant
from atril.errors import AtrilError
from atril.gui import tray
from atril.gui.model import (
    TOOLTIP_LIMIT,
    Action,
    CloseAction,
    Facts,
    TrayCommand,
    close_action,
    overall,
    service_states,
    tool_cards,
    tray_menu,
    tray_tooltip,
)
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
        tools={
            "git": True,
            "uv": True,
            "node": True,
            "npm": True,
            "python": True,
            "claude": True,
        },
        assistant=Assistant("claude_code", "claude-code/opus", False),
        ollama_required=True,
    )
    return dataclasses.replace(base, **changes)


def test_tool_cards_offer_one_action_each() -> None:
    cards = {card.key: card for card in tool_cards(_facts())}

    assert [c.key for c in tool_cards(_facts())] == [
        "deeptutor",
        "ollama",
        "python",
        "uv",
        "node",
        "npm",
        "git",
        "asistente",
    ]
    assert cards["deeptutor"].action is Action.START
    assert cards["ollama"].action is Action.NONE  # abierto aparte: no se para
    assert cards["git"].action is Action.NONE and cards["git"].level is Level.OK
    assert cards["asistente"].state == "Claude Code disponible"

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
                assistant=Assistant("ollama", "llama3:8b", False),
            )
        )
    }
    assert missing["deeptutor"].action is Action.INSTALL
    assert missing["ollama"].action is Action.INSTALL
    assert missing["asistente"].action is Action.PULL


def test_overall_and_footer_states() -> None:
    from atril.checks import error
    from atril.gui.model import Primary, primary

    assert overall(_facts())[:2] == (Level.INFO, "Parado")
    assert overall(_facts(backend_up=True, frontend_up=True))[0] is Level.OK
    assert overall(_facts(deeptutor_installed=False))[0] is Level.ERROR
    pending = _facts(pending=[warning("paginas-citas: pendiente")])
    assert overall(pending)[2] == "Parche pendiente."
    assert primary(pending) is Primary.PATCH
    broken = _facts(pending=[warning("a: pendiente"), error("b: ha cambiado")])
    assert overall(broken)[2] == "Parche no encaja con DeepTutor."
    assert primary(broken) is Primary.REVIEW
    assert primary(_facts(deeptutor_installed=False)) is Primary.INSTALL
    assert primary(_facts(backend_up=True)) is Primary.STOP
    no_git = _facts(tools={**_facts().tools, "git": False})
    assert overall(no_git)[2] == "Falta herramienta por instalar."
    assert service_states(_facts()) == {
        "DeepTutor": (Level.INFO, "Parado"),
        "Ollama": (Level.OK, "En marcha"),
    }


def test_source_rows_and_actions(station_dir) -> None:
    from atril.config import load_station, load_syllabus
    from atril.gui.model import (
        SyllabusData,
        actions_needed,
        document_path,
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
    # Doble clic en la Biblioteca: el documento de cada fila.
    assert document_path(syllabus, first.source_id) == path
    assert document_path(syllabus, "no-existe") is None


def test_close_hides_only_with_tray_and_deeptutor_running() -> None:
    def action(tray: bool, up: bool, busy: bool) -> CloseAction:
        return close_action(tray=tray, deeptutor_up=up, busy=busy)

    assert action(True, True, False) is CloseAction.HIDE
    assert action(True, True, True) is CloseAction.HIDE  # la operación sigue
    assert action(True, False, True) is CloseAction.WAIT
    assert action(True, False, False) is CloseAction.QUIT
    assert action(False, True, False) is CloseAction.ASK_STOP
    assert action(False, True, True) is CloseAction.WAIT


def test_tray_menu_follows_deeptutor_and_operation() -> None:
    menu = tray_menu(deeptutor_up=False, busy=True)
    items = {item.command: item for item in menu if item is not None}

    assert [i.command for i in menu if i and i.default] == [TrayCommand.SHOW]
    assert items[TrayCommand.TOGGLE].text == "Arrancar DeepTutor"
    assert not items[TrayCommand.OPEN].enabled
    assert not items[TrayCommand.TOGGLE].enabled
    assert not items[TrayCommand.BACKUP].enabled
    assert items[TrayCommand.QUIT].enabled
    assert menu[-1] is not None and menu[-1].command is TrayCommand.QUIT


def test_tray_tooltip_fits_windows_limit() -> None:
    text = tray_tooltip(deeptutor_up=False, status="x" * 300)

    assert len(text) == TOOLTIP_LIMIT
    assert text.endswith("...")
    assert tray_tooltip(deeptutor_up=False, status="") == "Atril: DeepTutor parado"


def test_tray_lifecycle() -> None:
    created = tray.create()
    if created is None:  # fuera de Windows no hay icono ni otra instancia
        assert not tray.signal_running()
        return
    try:
        created.menu = tray_menu(deeptutor_up=True, busy=False)
        created.set_tooltip("Atril: prueba")
        assert created.pending() == []
    finally:
        created.stop()


def test_activity_save_failure_is_reported_once(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atril.gui import activity as activity_module

    log = tmp_path / "diagnostico.log"
    monkeypatch.setattr(activity_module, "DIAGNOSTIC_LOG", log)
    blocked = tmp_path / "fichero"
    blocked.write_text("", encoding="utf-8")
    history = activity_module.ActivityLog(
        blocked / "actividad.jsonl"
    )  # padre = fichero

    for _ in range(2):
        event = history.start("Hacer backup")
        event.finish()
        history.save(event)  # no lanza: la operación sigue

    assert history.error is not None and "No se puede guardar" in history.error
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1  # una sola vez
    assert len(history.events) == 2  # siguen en memoria
