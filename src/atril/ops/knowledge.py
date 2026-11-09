"""Bases de conocimiento: estado, indexado y reindexado de las fuentes de un temario.

El indexado añade las fuentes nuevas **una a una** con el CLI de DeepTutor; el
reindexado sustituye las cambiadas y purga las retiradas con su API. Ambos
reservan la estación y se pueden cancelar: el indexado corta la fuente en curso
(al repetir continúa por ella), el reindexado deja de seguir a DeepTutor.
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from atril import ollama
from atril.checks import Finding, Level, error, info, ok, warning
from atril.config.station import Station
from atril.config.syllabus import KnowledgeBase, Syllabus
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError, CancelledError
from atril.install import Installer
from atril.knowledge import (
    POLL_SECONDS,
    RETRY_STATES,
    STALL_SECONDS,
    IndexedSource,
    Indexer,
    KbRun,
    KnowledgeApi,
    Ledger,
    PlanItem,
    PlanState,
    embedding_selection,
    ledger_path,
    plan,
)
from atril.lock import station_lock
from atril.net import HttpError
from atril.ops import Reporter, service
from atril.sources import now_iso

REINDEX_START_TIMEOUT = 60.0
"""Segundos que se espera a que DeepTutor publique el run del reindexado."""

RESTART_TIMEOUT = 900
"""Segundos de espera al arrancar DeepTutor para reindexar."""

RUN_LABELS = {
    "running": "en marcha",
    "completed": "completado",
    "failed": "fallido",
    "interrupted": "interrumpido",
    "cancelled": "cancelado",
    "partial": "parcial",
}
"""Estados de ``.indexing-run.json`` en español."""


@dataclass(frozen=True, slots=True)
class KbStatus:
    """Situación de una KB: cada fuente frente al registro y el último run."""

    kb: KnowledgeBase
    items: list[PlanItem]
    run: KbRun | None
    created: bool
    """La KB existe ya en DeepTutor."""
    needs_reindex: bool
    """Hay fuentes cambiadas o retiradas, o un reindexado sin terminar."""

    def count(self, state: PlanState) -> int:
        """Fuentes en ``state``."""
        return sum(item.state is state for item in self.items)


def select_kbs(syllabus: Syllabus, kb_id: str | None = None) -> list[KnowledgeBase]:
    """KB pedidas del temario (todas si no se indica).

    Raises:
        AtrilError: Si el temario no tiene esa KB.
    """
    if kb_id is None:
        return list(syllabus.knowledge_bases)
    for kb in syllabus.knowledge_bases:
        if kb.id == kb_id:
            return [kb]
    known = ", ".join(kb.id for kb in syllabus.knowledge_bases)
    raise AtrilError(
        f"el temario {syllabus.id} no tiene la KB {kb_id!r} (tiene: {known})."
    )


def status(
    station: Station, syllabus: Syllabus, kb_id: str | None = None
) -> tuple[list[KbStatus], list[Finding]]:
    """Estado de las KB del temario y avisos de lo pendiente; no modifica nada."""
    ledger = Ledger(ledger_path(syllabus))
    kbs = select_kbs(syllabus, kb_id)
    statuses = []
    unfinished: list[Finding] = []
    for kb in kbs:
        kb_dir = station.kb_dir(kb.id)
        items = plan(syllabus, kb, ledger)
        stale = {PlanState.CHANGED, PlanState.REMOVED}
        run = KbRun.load(kb_dir) if kb_dir.is_dir() else None
        broken = unfinished_rebuild(run)
        if broken:
            unfinished.append(
                warning(
                    f"{kb.id}: el último reindexado quedó "
                    f"{RUN_LABELS.get(run.state, run.state) if run else '?'}; "
                    "reindexa para completarlo."
                )
            )
        statuses.append(
            KbStatus(
                kb,
                items,
                run,
                (kb_dir / "metadata.json").is_file(),
                ledger.kb(kb.id).pending_reindex
                or broken
                or any(item.state in stale for item in items),
            )
        )
    return statuses, pending(syllabus, kbs, ledger) + unfinished


def unfinished_rebuild(run: KbRun | None) -> bool:
    """El último reindexado de DeepTutor no terminó (fallido, interrumpido...).

    Solo cuenta el reindexado: un añadido que no terminó deja su fuente por
    indexar, y eso se resuelve indexando.
    """
    return (
        run is not None
        and run.raw.get("action") == "rebuild"
        and run.state in RETRY_STATES
    )


def pending(
    syllabus: Syllabus, kbs: list[KnowledgeBase], ledger: Ledger
) -> list[Finding]:
    """Fuentes por indexar, sin fichero o KB que necesitan reindexarse."""
    findings: list[Finding] = []
    for kb in kbs:
        items = plan(syllabus, kb, ledger)
        new = [i.source_id for i in items if i.state is PlanState.NEW]
        removed = [i.source_id for i in items if i.state is PlanState.REMOVED]
        changed = [i.source_id for i in items if i.state is PlanState.CHANGED]
        missing = [i.source_id for i in items if i.state is PlanState.MISSING]
        if new:
            findings.append(info(f"{kb.id}: por indexar {', '.join(new)}."))
        if missing:
            findings.append(
                warning(
                    f"{kb.id}: sin fichero ({', '.join(missing)}); descárgalas antes."
                )
            )
        if ledger.kb(kb.id).pending_reindex or removed or changed:
            if changed:
                reason = f"fuentes cambiadas ({', '.join(changed)})"
            elif removed:
                reason = f"fuentes retiradas ({', '.join(removed)})"
            else:
                reason = "un reindexado sin terminar"
            findings.append(warning(f"{kb.id}: hay {reason}; hay que reindexarla."))
    return findings


def index(
    station: Station,
    syllabus: Syllabus,
    reporter: Reporter,
    kb_id: str | None = None,
    cancel: threading.Event | None = None,
) -> int:
    """Añade a sus KB las fuentes nuevas, una a una.

    Si se interrumpe o falla, al repetirlo continúa por la fuente pendiente y
    DeepTutor reutiliza el parseo en caché. Cambiadas y retiradas: :func:`reindex`.

    Returns:
        Número de fuentes indexadas.

    Raises:
        AtrilError: Si DeepTutor u Ollama no están listos o una fuente falla.
        CancelledError: Si se cancela (la fuente en curso queda pendiente).
    """
    with station_lock(station, "indexado"):
        kbs = select_kbs(syllabus, kb_id)
        dt = service.installed(station)
        ledger = Ledger(ledger_path(syllabus))
        todo = [
            (kb, item)
            for kb in kbs
            for item in plan(syllabus, kb, ledger)
            if item.state is PlanState.NEW
        ]
        if todo:
            preflight(station, reporter)
            apply_settings(station, dt, reporter)
            indexer = Indexer(station, dt.env())
            for number, (kb, item) in enumerate(todo, 1):
                counter = f"[{number}/{len(todo)}]"
                _index_one(indexer, ledger, kb, item, counter, reporter, cancel)
        if findings := pending(syllabus, kbs, ledger):
            reporter.show(findings, "Pendiente")
        return len(todo)


def reindex(
    station: Station,
    syllabus: Syllabus,
    kb: KnowledgeBase,
    reporter: Reporter,
    cancel: threading.Event | None = None,
) -> str:
    """Reindexa una KB: sustituye fuentes cambiadas y purga las retiradas.

    Arranca DeepTutor si hace falta (o lo reinicia si el último indexado dejó el
    worker colgado), quita las versiones anteriores, añade las nuevas y lanza el
    reindexado con el embedding activo. Al repetirlo continúa donde se quedó.

    Returns:
        Mensaje final para el usuario.

    Raises:
        AtrilError: Si algo falla; el mensaje dice cómo seguir.
    """
    with station_lock(station, "reindexado"):
        dt = service.installed(station)
        kb_dir = station.kb_dir(kb.id)
        if not (kb_dir / "metadata.json").is_file():
            raise AtrilError(
                f"la KB {kb.id} aún no existe; indexa antes {syllabus.id}."
            )
        before = KbRun.load(kb_dir)
        was_running = dt.backend_up()
        _ensure_running(dt, before, reporter)
        preflight(station, reporter)

        ledger = Ledger(ledger_path(syllabus))
        items = plan(syllabus, kb, ledger)
        removed = [item for item in items if item.state is PlanState.REMOVED]
        changed = [item for item in items if item.state is PlanState.CHANGED]
        api = KnowledgeApi(station)
        if removed or changed:
            old = removed + [_previous(ledger, kb, item) for item in changed]
            findings = _remove_files(api, kb, old)
            reporter.show(findings, "Versiones anteriores y retiradas")
            if any(f.level is Level.ERROR for f in findings):
                raise AtrilError("no se han podido quitar todas; revisa y repite.")
        indexer = Indexer(station, dt.env())
        for number, item in enumerate(changed, 1):
            counter = f"[{number}/{len(changed)}]"
            _index_one(indexer, ledger, kb, item, counter, reporter, cancel)

        # Los añadidos de arriba dejan su propio run: el reindexado se reconoce
        # por su tarea, no por ser distinto del que había al empezar.
        before = KbRun.load(kb_dir)
        if before is not None and before.state == "running":
            reporter.show(
                [info("Ya hay un indexado en curso en esta KB; se sigue su progreso.")]
            )
        else:
            selection = embedding_selection(station, dt.env())
            if selection == "{}":
                raise AtrilError(
                    "DeepTutor no tiene modelo de embedding activo; reinstálalo."
                )
            try:
                reply = api.reindex(kb.id, selection)
            except OSError as exc:
                raise AtrilError(
                    f"no se ha podido lanzar el reindexado: {exc}"
                ) from exc
            if reply.get("noop"):
                _finish_reindex(ledger, kb, removed)
                return f"DeepTutor indica que no hace falta: {reply.get('message', '')}"
            task = reply.get("task_id")
            reporter.show([info(f"Reindexado lanzado (tarea {task or '?'}).")])
            _wait_new_run(kb_dir, before, str(task) if task else None)

        run = _follow(kb_dir, reporter, cancel)
        if run is None or run.state != "completed":
            message = run.error if run else "sin estado"
            hint = (
                " Mira si otra app ha cargado un modelo en la GPU."
                if "11434" in message
                else ""
            )
            state = run.state if run else "?"
            raise AtrilError(
                f"el reindexado ha terminado como {state}: {message}.{hint}"
            )
        _finish_reindex(ledger, kb, removed)
        if not was_running:
            # Se arrancó solo para reindexar: se deja como estaba.
            service.stop(dt, reporter)
        return f"KB {kb.id} reindexada."


def preflight(station: Station, reporter: Reporter) -> None:
    """Ollama responde, no hay modelos ajenos en VRAM y el embedding funciona.

    Raises:
        AtrilError: Si falta ``[ollama]`` o el embedding no funciona.
    """
    config = station.require_ollama()
    current = ollama.get_status(config.url)
    findings = [f for f in ollama.check(current, config) if f.level is not Level.OK]
    if not any(finding.level is Level.ERROR for finding in findings):
        with reporter.busy(f"Cargando {config.embedding} en Ollama..."):
            findings.extend(ollama.probe_embedding(config))
        # Ya cargado, se ve si cabe entero en la VRAM.
        loaded = ollama.get_status(config.url)
        findings.extend(
            w for w in ollama.offload_warnings(loaded, config) if w not in findings
        )
    if findings:
        reporter.show(findings, "Ollama")
    if any(finding.level is Level.ERROR for finding in findings):
        raise AtrilError("corrige el embedding antes de indexar.")


def apply_settings(station: Station, dt: DeepTutor, reporter: Reporter) -> None:
    """Aplica ``[indexado]`` a DeepTutor (parser, chunks y ritmo del embedding).

    Así un cambio en ``atril.toml`` vale para este indexado sin reinstalar.
    """
    reporter.show(
        Installer(station, dt.env()).runtime_settings(), "Ajustes de indexado"
    )


def _index_one(
    indexer: Indexer,
    ledger: Ledger,
    kb: KnowledgeBase,
    item: PlanItem,
    counter: str,
    reporter: Reporter,
    cancel: threading.Event | None,
) -> None:
    """Añade una fuente y la apunta en el registro; lanza error si falla."""
    if cancel is not None and cancel.is_set():
        raise CancelledError("indexado cancelado; vuelve a indexar para continuar.")
    label = f"{counter} {kb.id} ← {item.file}"
    warned = False
    with reporter.busy(label) as update:

        def tick(run: KbRun | None, elapsed: float) -> None:
            nonlocal warned
            if cancel is not None and cancel.is_set():
                raise CancelledError(
                    f"indexado cancelado en {item.file}; al volver a indexar "
                    "continúa por ella (reutiliza el parseo en caché)."
                )
            now = time.time()
            detail = run.describe(now) if run else "arrancando"
            update(f"{label} · {int(elapsed // 60)} min · {detail}")
            idle = run.idle_seconds(now) if run else None
            if not warned and idle is not None and idle > STALL_SECONDS:
                warned = True
                reporter.show(
                    [
                        warning(
                            f"Sin actividad desde hace {int(idle // 60)} min. Si "
                            "sigue así, cancela y vuelve a indexar para continuar."
                        )
                    ]
                )

        result = indexer.add(kb.id, item, tick)

    if not result.ok:
        tail: list[str] = []
        if result.log is not None and result.log.is_file():
            text = result.log.read_text(encoding="utf-8", errors="replace")
            tail = text.splitlines()[-25:]
        raise AtrilError(
            f"{item.file}: {result.detail}. Vuelve a indexar para reintentar "
            "(reutiliza el parseo en caché).",
            log=tail,
            log_title=str(result.log or ""),
        )
    entry = ledger.kb(kb.id)
    entry.sources[item.source_id] = IndexedSource(
        item.file, item.digest, now_iso(), round(result.minutes, 1)
    )
    if item.state is PlanState.CHANGED:
        entry.pending_reindex = True
    ledger.save()
    extra = f" ({result.detail})" if result.detail else ""
    reporter.show([ok(f"{counter} {item.file} en {result.minutes:.1f} min{extra}.")])


def _ensure_running(dt: DeepTutor, before: KbRun | None, reporter: Reporter) -> None:
    """Arranca DeepTutor, o lo reinicia si el último indexado dejó el worker colgado."""
    running = dt.backend_up()
    if running and before is not None and before.state in RETRY_STATES:
        reporter.show(
            [
                warning(
                    f"El último indexado terminó como '{before.state}': se reinicia "
                    "DeepTutor para liberar el worker."
                )
            ]
        )
        service.stop(dt, reporter)
        running = False
    if not running:
        service.start(dt, reporter, RESTART_TIMEOUT)


def _remove_files(
    api: KnowledgeApi, kb: KnowledgeBase, items: list[PlanItem]
) -> list[Finding]:
    """Quita de la KB los documentos de versiones anteriores y fuentes retiradas."""
    findings: list[Finding] = []
    for item in items:
        try:
            api.delete_file(kb.id, item.file)
            findings.append(info(f"{item.file}: quitado de la KB."))
        except HttpError as exc:
            if exc.status == 404:
                findings.append(info(f"{item.file}: ya no estaba en la KB."))
            else:
                findings.append(error(f"{item.file}: {exc.detail}"))
        except OSError as exc:
            findings.append(error(f"{item.file}: {exc}"))
    return findings


def _wait_new_run(kb_dir: Path, before: KbRun | None, task: str | None) -> None:
    """Espera a que DeepTutor publique el run del reindexado lanzado.

    Con la tarea que devuelve la API se espera exactamente ese run. DeepTutor lo
    escribe al empezar, poco después de responder: hasta entonces el fichero
    sigue con el run anterior (por ejemplo, el de un añadido ya completado).
    """
    deadline = time.monotonic() + REINDEX_START_TIMEOUT
    while time.monotonic() < deadline:
        run = KbRun.load(kb_dir)
        if run is not None and (
            run.task_id == task
            if task
            else before is None or run.task_id != before.task_id
        ):
            return
        time.sleep(1)
    raise AtrilError("DeepTutor no ha empezado el reindexado; revisa su log.")


def _follow(
    kb_dir: Path, reporter: Reporter, cancel: threading.Event | None
) -> KbRun | None:
    """Sigue el run hasta que termina, con avance y aviso de bloqueo."""
    started = time.monotonic()
    warned = False
    run = KbRun.load(kb_dir)
    with reporter.busy("Reindexando...") as update:
        while run is not None and run.state == "running":
            if cancel is not None and cancel.is_set():
                raise CancelledError(
                    "se deja de seguir el reindexado; DeepTutor sigue con él. "
                    "Repite para seguirlo."
                )
            time.sleep(POLL_SECONDS)
            run = KbRun.load(kb_dir)
            if run is None:
                continue
            now = time.time()
            minutes = int((time.monotonic() - started) // 60)
            update(f"Reindexando · {minutes} min · {run.describe(now)}")
            idle = run.idle_seconds(now)
            if not warned and idle is not None and idle > STALL_SECONDS:
                warned = True
                reporter.show(
                    [
                        warning(
                            "Sin actividad desde hace más de 15 min. Si sigue así, "
                            "para DeepTutor y repite el reindexado (reanuda)."
                        )
                    ]
                )
    return run


def _previous(ledger: Ledger, kb: KnowledgeBase, item: PlanItem) -> PlanItem:
    """Versión indexada de una fuente cambiada (con su nombre en la KB)."""
    recorded = ledger.kb(kb.id).sources[item.source_id]
    return PlanItem(item.source_id, PlanState.REMOVED, file=recorded.file)


def _finish_reindex(ledger: Ledger, kb: KnowledgeBase, removed: list[PlanItem]) -> None:
    """Actualiza el registro tras un reindexado correcto."""
    entry = ledger.kb(kb.id)
    for item in removed:
        entry.sources.pop(item.source_id, None)
    entry.pending_reindex = False
    ledger.save()
