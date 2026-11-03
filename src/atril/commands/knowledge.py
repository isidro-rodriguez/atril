"""Comandos de KB: ``atril kb indexar`` y ``atril kb reindexar``."""

import time
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from atril import ollama
from atril.checks import Finding, Level, error, info, ok, warning
from atril.commands._common import (
    console,
    fail,
    find_kb,
    get_station,
    get_syllabus,
    show,
    success,
)
from atril.commands.deeptutor import launch, shutdown
from atril.config.station import Station
from atril.config.syllabus import KnowledgeBase, Syllabus
from atril.deeptutor import DeepTutor
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
from atril.net import HttpError
from atril.sources import now_iso

kb_app = typer.Typer(
    help="Bases de conocimiento: indexado, reindexado y evaluación.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

_STATE_STYLE = {
    PlanState.INDEXED: "green",
    PlanState.NEW: "cyan",
    PlanState.CHANGED: "bold yellow",
    PlanState.MISSING: "yellow",
    PlanState.REMOVED: "bold red",
}

REINDEX_START_TIMEOUT = 60.0
"""Segundos que se espera a que DeepTutor publique el run del reindexado."""


@kb_app.command("indexar")
def index(
    ctx: typer.Context,
    syllabus_id: Annotated[str, typer.Argument(help="Id del temario.")],
    kb_id: Annotated[
        str | None, typer.Argument(help="KB del temario; por defecto, todas.")
    ] = None,
) -> None:
    """Añade a sus KB las fuentes nuevas, [bold]una a una[/].

    Si se interrumpe o falla, vuelve a ejecutar el mismo comando: continúa por la
    fuente pendiente y DeepTutor reutiliza el parseo en caché. Las fuentes
    cambiadas o retiradas se resuelven con [bold]atril kb reindexar[/].
    """
    station = get_station(ctx)
    syllabus = get_syllabus(ctx, syllabus_id)
    kbs = _kbs(syllabus, kb_id)
    dt = DeepTutor(station)
    if not dt.installed:
        fail("DeepTutor no está instalado; usa atril instalar.")

    ledger = Ledger(ledger_path(syllabus))
    plans = {kb.id: plan(syllabus, kb, ledger) for kb in kbs}
    for kb in kbs:
        _show_plan(kb, plans[kb.id])
    todo = [
        (kb, item) for kb in kbs for item in plans[kb.id] if item.state is PlanState.NEW
    ]
    if not todo:
        _show_pending(syllabus, kbs, ledger)
        success("Nada que indexar.")
        return

    if not show(_embedding_preflight(station), "Ollama"):
        fail("corrige el embedding antes de indexar.")

    indexer = Indexer(station, dt.env())
    for number, (kb, item) in enumerate(todo, 1):
        _index_one(indexer, ledger, kb, item, f"[{number}/{len(todo)}]")
    _show_pending(syllabus, kbs, ledger)
    success("Indexado completo.")


@kb_app.command("reindexar")
def reindex(
    ctx: typer.Context,
    kb_id: Annotated[str, typer.Argument(help="Id de la KB (único en la estación).")],
) -> None:
    """Reindexa una KB: sustituye fuentes cambiadas y purga las retiradas.

    Necesita DeepTutor en marcha (lo arranca si hace falta). Quita de la KB las
    versiones anteriores y las fuentes retiradas, añade las versiones nuevas y
    rehace chunks y embeddings reutilizando el parseo en caché. Si se interrumpe,
    al repetir el comando continúa donde se quedó.
    """
    station = get_station(ctx)
    syllabus, kb = find_kb(ctx, kb_id)
    dt = DeepTutor(station)
    if not dt.installed:
        fail("DeepTutor no está instalado; usa atril instalar.")
    kb_dir = station.kb_dir(kb.id)
    if not (kb_dir / "metadata.json").is_file():
        fail(
            f"la KB {kb.id} todavía no existe; "
            f"créala con: atril kb indexar {syllabus.id}"
        )

    before = KbRun.load(kb_dir)
    _ensure_running(dt, before)
    if not show(_embedding_preflight(station), "Ollama"):
        fail("corrige el embedding antes de reindexar.")

    ledger = Ledger(ledger_path(syllabus))
    items = plan(syllabus, kb, ledger)
    removed = [item for item in items if item.state is PlanState.REMOVED]
    changed = [item for item in items if item.state is PlanState.CHANGED]
    api = KnowledgeApi(station)
    if removed or changed:
        old = removed + [_previous(ledger, kb, item) for item in changed]
        if not show(_remove_files(api, kb, old), "Versiones anteriores y retiradas"):
            fail("no se han podido quitar todas; revisa los errores y repite.")
    indexer = Indexer(station, dt.env())
    for number, item in enumerate(changed, 1):
        _index_one(indexer, ledger, kb, item, f"[{number}/{len(changed)}]")

    if before is not None and before.state == "running":
        show(
            [info("Ya hay un indexado en curso en esta KB; solo se sigue su progreso.")]
        )
    else:
        selection = embedding_selection(station, dt.env())
        if selection == "{}":
            fail(
                "DeepTutor no tiene modelo de embedding activo; ejecuta atril instalar."
            )
        try:
            reply = api.reindex(kb.id, selection)
        except OSError as exc:
            fail(f"no se ha podido lanzar el reindexado: {exc}")
        if reply.get("noop"):
            _finish_reindex(ledger, kb, removed)
            show(
                [
                    info(
                        "DeepTutor indica que no hace falta: "
                        f"{reply.get('message', '')}"
                    )
                ]
            )
            return
        show([info(f"Reindexado lanzado (tarea {reply.get('task_id', '?')}).")])
        _wait_new_run(kb_dir, before)

    run = _follow(kb_dir)
    if run is None or run.state != "completed":
        message = run.error if run else "sin estado"
        hint = (
            " Mira si otra app ha cargado un modelo en la GPU."
            if "11434" in message
            else ""
        )
        fail(
            f"el reindexado ha terminado como {run.state if run else '?'}: "
            f"{message}.{hint}"
        )
    _finish_reindex(ledger, kb, removed)
    success(f"KB {kb.id} reindexada.")


# --- indexado ------------------------------------------------------------------


def _kbs(syllabus: Syllabus, kb_id: str | None) -> list[KnowledgeBase]:
    """KB pedidas del temario."""
    if kb_id is None:
        return list(syllabus.knowledge_bases)
    for kb in syllabus.knowledge_bases:
        if kb.id == kb_id:
            return [kb]
    known = ", ".join(kb.id for kb in syllabus.knowledge_bases)
    fail(f"el temario {syllabus.id} no tiene la KB {kb_id!r} (tiene: {known}).")


def _show_plan(kb: KnowledgeBase, items: list[PlanItem]) -> None:
    """Tabla con la situación de cada fuente de la KB."""
    table = Table("Fuente", "Fichero", "Estado", title=f"KB [bold]{escape(kb.id)}[/]")
    table.title_justify = "left"
    for item in items:
        style = _STATE_STYLE[item.state]
        table.add_row(
            escape(item.source_id), escape(item.file), f"[{style}]{item.state}[/]"
        )
    console.print(table)


def _index_one(
    indexer: Indexer, ledger: Ledger, kb: KnowledgeBase, item: PlanItem, counter: str
) -> None:
    """Añade una fuente con indicador de avance; termina con error si falla."""
    label = f"{counter} {escape(kb.id)} ← {escape(item.file)}"
    warned = False

    def tick(run: KbRun | None, elapsed: float) -> None:
        nonlocal warned
        now = time.time()
        detail = escape(run.describe(now)) if run else "arrancando"
        status.update(f"{label} · {int(elapsed // 60)} min · {detail}")
        idle = run.idle_seconds(now) if run else None
        if not warned and idle is not None and idle > STALL_SECONDS:
            warned = True
            console.print(
                f"  [yellow]! Sin actividad desde hace {int(idle // 60)} min. "
                "Si sigue así, Ctrl+C y vuelve a ejecutar para continuar.[/]"
            )

    try:
        with console.status(label) as status:
            result = indexer.add(kb.id, item, tick)
    except KeyboardInterrupt:
        console.print(
            "[yellow]Interrumpido. Vuelve a ejecutar el comando para continuar.[/]"
        )
        raise typer.Exit(130) from None

    if not result.ok:
        if result.log is not None and result.log.is_file():
            tail = result.log.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()[-25:]
            console.print(
                Panel(
                    escape("\n".join(tail)),
                    title=escape(str(result.log)),
                    title_align="left",
                    border_style="red",
                )
            )
        fail(
            f"{item.file}: {result.detail}. Vuelve a ejecutar el comando para "
            "reintentar (reutiliza el parseo en caché)."
        )

    entry = ledger.kb(kb.id)
    entry.sources[item.source_id] = IndexedSource(
        item.file, item.digest, now_iso(), round(result.minutes, 1)
    )
    if item.state is PlanState.CHANGED:
        entry.pending_reindex = True
    ledger.save()
    extra = f" ({result.detail})" if result.detail else ""
    show([ok(f"{counter} {item.file} en {result.minutes:.1f} min{extra}.")])


def _show_pending(syllabus: Syllabus, kbs: list[KnowledgeBase], ledger: Ledger) -> None:
    """Avisa de KB que necesitan reindexarse y de fuentes sin fichero."""
    findings: list[Finding] = []
    for kb in kbs:
        items = plan(syllabus, kb, ledger)
        removed = [i.source_id for i in items if i.state is PlanState.REMOVED]
        changed = [i.source_id for i in items if i.state is PlanState.CHANGED]
        missing = [i.source_id for i in items if i.state is PlanState.MISSING]
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
            findings.append(
                warning(f"{kb.id}: hay {reason}; ejecuta atril kb reindexar {kb.id}")
            )
    if findings:
        show(findings, "Pendiente")


# --- reindexado ----------------------------------------------------------------


def _embedding_preflight(station: Station) -> list[Finding]:
    """Ollama responde, no hay modelos ajenos en VRAM y el embedding funciona."""
    status = ollama.get_status(station.ollama.url)
    findings = [
        f for f in ollama.check(status, station.ollama) if f.level is not Level.OK
    ]
    if any(finding.level is Level.ERROR for finding in findings):
        return findings
    with console.status(f"Cargando {escape(station.ollama.embedding)} en Ollama..."):
        findings.extend(ollama.probe_embedding(station.ollama))
    return findings


def _ensure_running(dt: DeepTutor, before: KbRun | None) -> None:
    """Arranca DeepTutor, o lo reinicia si el último indexado dejó el worker colgado."""
    running = dt.backend_up()
    if running and before is not None and before.state in RETRY_STATES:
        show(
            [
                warning(
                    f"El último indexado terminó como '{before.state}': se reinicia "
                    "DeepTutor para liberar el worker."
                )
            ]
        )
        shutdown(dt)
        running = False
    if not running:
        launch(dt, timeout=900)


def _remove_files(
    api: KnowledgeApi, kb: KnowledgeBase, items: list[PlanItem]
) -> list[Finding]:
    """Quita de la KB los documentos de fuentes retiradas del temario."""
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


def _wait_new_run(kb_dir: Path, before: KbRun | None) -> None:
    """Espera a que DeepTutor publique el run del nuevo reindexado."""
    deadline = time.monotonic() + REINDEX_START_TIMEOUT
    while time.monotonic() < deadline:
        run = KbRun.load(kb_dir)
        if run is not None and (before is None or run.task_id != before.task_id):
            return
        time.sleep(1)
    fail("DeepTutor no ha empezado el reindexado; revisa su log.")


def _follow(kb_dir: Path) -> KbRun | None:
    """Sigue el run hasta que termina, con avance y aviso de bloqueo."""
    started = time.monotonic()
    warned = False
    run = KbRun.load(kb_dir)
    with console.status("Reindexando...") as status:
        while run is not None and run.state == "running":
            time.sleep(POLL_SECONDS)
            run = KbRun.load(kb_dir)
            if run is None:
                continue
            now = time.time()
            minutes = int((time.monotonic() - started) // 60)
            status.update(f"Reindexando · {minutes} min · {escape(run.describe(now))}")
            idle = run.idle_seconds(now)
            if not warned and idle is not None and idle > STALL_SECONDS:
                warned = True
                console.print(
                    "  [yellow]! Sin actividad desde hace más de 15 min. Si sigue así: "
                    "atril parar, y repite este comando (reanuda).[/]"
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
