import threading

from atril.checks import error, info, ok, warning
from atril.errors import AtrilError
from atril.gui.model import overall, summarize
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


def test_summary_rows_and_overall_level() -> None:
    sections = [
        ("DeepTutor", [ok("Instalado en app."), ok("En marcha: http://x")]),
        ("Ollama", [info("Sin [ollama]")]),
        ("Estación y copias", [ok("50 GiB libres"), warning("Copia de hace 9 días")]),
    ]

    rows = summarize(sections)

    assert [row.message for row in rows] == [
        "En marcha: http://x",
        "Sin [ollama]",
        "Copia de hace 9 días",
    ]
    assert overall(rows)[0].value == "aviso"
    assert overall(summarize([("DeepTutor", [error("No instalado")])]))[0].value == (
        "error"
    )
    assert overall(summarize(sections[:2]))[0].value == "ok"
