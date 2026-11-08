"""Fuentes de un temario: descargar las que faltan y buscar versiones nuevas."""

import threading
import time
from collections.abc import Callable

from acodo.utils import get_now, parse_size

from atril.config import Syllabus
from atril.config.syllabus import Source
from atril.errors import AtrilError, CancelledError
from atril.ops import Reporter, Update
from atril.sources import Outcome, Result, SourceManager, is_due
from atril.sources import Progress as SourceProgress

UPDATE_SECONDS = 0.25
"""Intervalo mínimo entre avisos de avance de una descarga."""


def select(syllabus: Syllabus, source_ids: list[str] | None = None) -> list[Source]:
    """Fuentes pedidas, en el orden del temario (todas si no se indica ninguna).

    Raises:
        AtrilError: Si algún id no existe en el temario.
    """
    if not source_ids:
        return list(syllabus.sources)
    known = {source.id: source for source in syllabus.sources}
    unknown = [item for item in source_ids if item not in known]
    if unknown:
        raise AtrilError(
            f"fuentes desconocidas en {syllabus.id}: {', '.join(unknown)}."
        )
    return [known[item] for item in source_ids]


def download(
    syllabus: Syllabus,
    reporter: Reporter,
    source_ids: list[str] | None = None,
    cancel: threading.Event | None = None,
) -> list[Result]:
    """Descarga las fuentes que faltan; no toca las que ya están en disco.

    Raises:
        AtrilError: Si el registro de fuentes no es válido o un id no existe.
        CancelledError: Si se cancela entre una fuente y otra.
    """
    manager = SourceManager(syllabus)
    return _each(manager, select(syllabus, source_ids), reporter, cancel, manager.fetch)


def check(
    syllabus: Syllabus,
    reporter: Reporter,
    source_ids: list[str] | None = None,
    *,
    check_all: bool = False,
    cancel: threading.Event | None = None,
) -> tuple[list[Result], int]:
    """Busca versiones nuevas; la anterior va al histórico.

    Sin ids ni ``check_all`` solo revisa las que tocan según ``comprobar``.

    Returns:
        Resultados y número de fuentes que aún no tocaba revisar.
    """
    manager = SourceManager(syllabus)
    now = get_now()
    candidates = [source for source in select(syllabus, source_ids) if source.url]
    explicit = bool(source_ids) or check_all
    due = [
        s for s in candidates if explicit or is_due(s, manager.registry.get(s.id), now)
    ]
    results = _each(manager, due, reporter, cancel, manager.check)
    return results, len(candidates) - len(due)


def changed_kbs(syllabus: Syllabus, results: list[Result]) -> list[str]:
    """KB con versiones nuevas, que hay que reindexar."""
    return sorted(
        {syllabus.kb_of(r.source).id for r in results if r.outcome is Outcome.UPDATED}
    )


def _each(
    manager: SourceManager,
    sources: list[Source],
    reporter: Reporter,
    cancel: threading.Event | None,
    action: Callable[[Source, SourceProgress], Result],
) -> list[Result]:
    """Aplica ``action`` a cada fuente y guarda el registro tras cada una."""
    results = []
    for number, source in enumerate(sources, 1):
        if cancel is not None and cancel.is_set():
            raise CancelledError("cancelado; las fuentes ya hechas quedan guardadas.")
        label = f"[{number}/{len(sources)}] {source.id}"
        with reporter.busy(label) as update:
            results.append(action(source, _throttled(label, update)))
        manager.registry.save()
    return results


def _throttled(label: str, update: Update) -> SourceProgress:
    """Avance de una descarga en texto, como mucho cada ``UPDATE_SECONDS``."""
    last = 0.0

    def progress(done: int, total: int | None) -> None:
        nonlocal last
        now = time.monotonic()
        if now - last < UPDATE_SECONDS:
            return
        last = now
        size = parse_size(done) + (f" de {parse_size(total)}" if total else "")
        update(f"{label} · {size}")

    return progress
