"""Comandos de KB: ``atril kb estado``, ``indexar``, ``reindexar`` y ``evaluar``."""

import time
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

from atril import ollama
from atril.checks import Finding, Level, error, info, ok, warning
from atril.commands._common import (
    console,
    fail,
    find_kb,
    get_station,
    get_syllabus,
    load_or_fail,
    show,
    success,
)
from atril.commands.deeptutor import launch, shutdown
from atril.config import ConfigError, load_syllabi
from atril.config.station import Station
from atril.config.syllabus import KnowledgeBase, Syllabus
from atril.deeptutor import DeepTutor
from atril.evaluation import (
    EvalReport,
    EvaluationError,
    previous_report,
    reports_dir,
    run_evaluation,
)
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


_STATE_COLUMNS = (
    ("Indexadas", PlanState.INDEXED),
    ("Nuevas", PlanState.NEW),
    ("Cambiadas", PlanState.CHANGED),
    ("Faltan", PlanState.MISSING),
    ("Retiradas", PlanState.REMOVED),
)
"""Columnas de ``kb estado``: cada fuente cuenta en una sola."""


@kb_app.command("estado")
def status(
    ctx: typer.Context,
    syllabus_id: Annotated[
        str | None,
        typer.Argument(metavar="TEMARIO", help="Id del temario; por defecto, todos."),
    ] = None,
    kb_id: Annotated[
        str | None,
        typer.Argument(metavar="KB", help="KB del temario; por defecto, todas."),
    ] = None,
    detail: Annotated[
        bool, typer.Option("--detalle", help="Muestra también cada fuente de cada KB.")
    ] = False,
) -> None:
    """Muestra qué fuentes están indexadas en cada KB, sin modificar nada.

    Compara los ficheros con [bold]fuentes/indexado.json[/] y añade el estado del
    último indexado de DeepTutor (p. ej. uno en marcha).
    """
    station = get_station(ctx)
    if syllabus_id is None:
        try:
            syllabi, _ = load_syllabi(station.syllabi_dir)
        except ConfigError as exc:
            fail(str(exc))
    else:
        syllabi = [get_syllabus(ctx, syllabus_id)]
    if kb_id is not None and len(syllabi) != 1:
        fail("indica el temario para elegir una KB.")

    table = Table(title="Indexado", title_justify="left")
    widest = max((len(kb.id) for s in syllabi for kb in s.knowledge_bases), default=2)
    table.add_column("KB", no_wrap=True, min_width=widest)
    table.add_column("Total", justify="right")
    for column, _ in _STATE_COLUMNS:
        table.add_column(column, justify="right")
    table.add_column("DeepTutor")
    findings: list[Finding] = []
    for syllabus in syllabi:
        kbs = _kbs(syllabus, kb_id)
        ledger = load_or_fail(lambda s=syllabus: Ledger(ledger_path(s)))
        for kb in kbs:
            items = plan(syllabus, kb, ledger)
            if detail:
                _show_plan(kb, items)
            counts = [
                sum(i.state is state for i in items) for _, state in _STATE_COLUMNS
            ]
            table.add_row(
                escape(kb.id),
                str(len(items) - counts[-1]),
                *(
                    _count(n, state)
                    for n, (_, state) in zip(counts, _STATE_COLUMNS, strict=True)
                ),
                _run_state(station, kb),
            )
            new = [i.source_id for i in items if i.state is PlanState.NEW]
            if new:
                findings.append(
                    info(
                        f"{kb.id}: por indexar {', '.join(new)}; ejecuta atril kb "
                        f"indexar {syllabus.id} {kb.id}"
                    )
                )
        findings.extend(_pending(syllabus, kbs, ledger))
    console.print(table)
    show(findings or [ok("Todas las fuentes con fichero están indexadas.")])


_RUN_LABELS = {
    "running": "en marcha",
    "completed": "completado",
    "failed": "fallido",
    "interrupted": "interrumpido",
    "cancelled": "cancelado",
    "partial": "parcial",
}
"""Estados de ``.indexing-run.json`` en español."""


def _count(number: int, state: PlanState) -> str:
    """Celda de recuento, coloreada si no es cero."""
    if not number:
        return "0"
    return f"[{_STATE_STYLE[state]}]{number}[/]"


def _run_state(station: Station, kb: KnowledgeBase) -> str:
    """Último indexado de DeepTutor para la KB, en una celda."""
    kb_dir = station.kb_dir(kb.id)
    if not kb_dir.is_dir():
        return "[dim]sin crear[/]"
    run = KbRun.load(kb_dir)
    if run is None:
        return "[dim]sin registro[/]"
    state = run.state
    label = escape(_RUN_LABELS.get(state, state) or "?")
    if state == "running":
        return f"[cyan]{label}[/] · {escape(run.describe(time.time()))}"
    if state in RETRY_STATES:
        return f"[bold yellow]{label}[/]"
    return label


@kb_app.command("indexar")
def index(
    ctx: typer.Context,
    syllabus_id: Annotated[
        str, typer.Argument(metavar="TEMARIO", help="Id del temario.")
    ],
    kb_id: Annotated[
        str | None,
        typer.Argument(metavar="KB", help="KB del temario; por defecto, todas."),
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

    ledger = load_or_fail(lambda: Ledger(ledger_path(syllabus)))
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
    kb_id: Annotated[
        str, typer.Argument(metavar="KB", help="Id de la KB (único en la estación).")
    ],
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
    _require_kb(station, syllabus, kb)
    kb_dir = station.kb_dir(kb.id)

    before = KbRun.load(kb_dir)
    _ensure_running(dt, before)
    if not show(_embedding_preflight(station), "Ollama"):
        fail("corrige el embedding antes de reindexar.")

    ledger = load_or_fail(lambda: Ledger(ledger_path(syllabus)))
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


@kb_app.command("evaluar")
def evaluate(
    ctx: typer.Context,
    kb_id: Annotated[
        str, typer.Argument(metavar="KB", help="Id de la KB (único en la estación).")
    ],
    top_k: Annotated[
        int,
        typer.Option("--k", "-k", min=1, help="Posiciones que cuentan como acierto."),
    ] = 5,
    dataset: Annotated[
        Path | None,
        typer.Option(
            "--dataset",
            exists=True,
            dir_okay=False,
            help="Preguntas (.jsonl); por defecto, la 'evaluacion' de la KB.",
        ),
    ] = None,
    detail: Annotated[
        bool,
        typer.Option(
            "--detalle", help="Muestra los fragmentos de todas las preguntas."
        ),
    ] = False,
) -> None:
    """Evalúa la recuperación de una KB comparando con el [bold]texto completo[/].

    Guarda el informe en el temario (eval/informes/) y compara las métricas con
    el informe anterior de la misma KB y conjunto de preguntas.
    """
    station = get_station(ctx)
    syllabus, kb = find_kb(ctx, kb_id)
    dt = DeepTutor(station)
    if not dt.installed:
        fail("DeepTutor no está instalado; usa atril instalar.")
    _require_kb(station, syllabus, kb)
    questions = dataset or (syllabus.root / kb.eval_file if kb.eval_file else None)
    if questions is None:
        fail(f"la KB {kb.id} no declara 'evaluacion' en temario.toml; usa --dataset.")
    if not questions.is_file():
        fail(f"no existe el conjunto de preguntas {questions}.")
    if not show(_embedding_preflight(station), "Ollama"):
        fail("corrige el embedding antes de evaluar.")

    folder = reports_dir(syllabus)
    before = previous_report(folder, kb.id, questions.name, top_k)
    with Progress(
        TextColumn(f"Evaluando {escape(kb.id)}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("", total=None)
        try:
            report = run_evaluation(
                station,
                dt.env(),
                kb.id,
                questions,
                top_k,
                lambda done, total: progress.update(task, completed=done, total=total),
            )
        except EvaluationError as exc:
            fail(str(exc))

    _show_cases(report, detail)
    _show_metrics(report, before)
    path = report.save(folder)
    console.print(f"Informe: [cyan]{escape(str(path.relative_to(syllabus.root)))}[/]")
    if any(case.error for case in report.cases):
        fail("algunas preguntas han dado error; revisa la tabla.")


# --- indexado ------------------------------------------------------------------


def _require_kb(station: Station, syllabus: Syllabus, kb: KnowledgeBase) -> None:
    """Termina con error si la KB aún no existe en DeepTutor."""
    if not (station.kb_dir(kb.id) / "metadata.json").is_file():
        fail(f"la KB {kb.id} aún no existe; créala con: atril kb indexar {syllabus.id}")


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
    if findings := _pending(syllabus, kbs, ledger):
        show(findings, "Pendiente")


def _pending(
    syllabus: Syllabus, kbs: list[KnowledgeBase], ledger: Ledger
) -> list[Finding]:
    """KB que necesitan reindexarse y fuentes sin fichero."""
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
    return findings


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


def _show_cases(report: EvalReport, detail: bool) -> None:
    """Tabla de preguntas: acierto y posición, o fallo con lo que se recuperó."""
    table = Table("Caso", "Resultado", "Pregunta", "Recuperado", title="Preguntas")
    table.title_justify = "left"
    for case in report.cases:
        if case.error:
            result = "[bold red]error[/]"
        elif case.rank is None:
            result = "[bold yellow]fallo[/]"
        else:
            style = "green" if case.rank == 1 else "cyan"
            result = f"[{style}]rango {case.rank}[/]"
        show_hits = detail or case.rank is None or bool(case.error)
        hits = (
            "\n".join(f"{h.title} p.{h.page or '?'}" for h in case.hits[:3])
            if show_hits
            else ""
        )
        table.add_row(
            escape(case.case_id),
            result,
            escape(case.query),
            escape(case.error or hits),
        )
    console.print(table)


def _show_metrics(report: EvalReport, before: EvalReport | None) -> None:
    """Métricas, con la diferencia respecto al informe anterior si lo hay."""
    columns = ["Métrica", "Valor"]
    if before:
        columns += [f"Anterior ({before.created_at[:10]})", "Cambio"]
    table = Table(*columns, title=f"Métricas (k={report.k})")
    table.title_justify = "left"
    for key, value in report.metrics.items():
        row = [escape(key), _metric(value)]
        if before:
            old = before.metrics.get(key)
            row.append(_metric(old) if old is not None else "—")
            row.append(_delta(key, value, old))
        table.add_row(*row)
    console.print(table)


def _metric(value: float | int) -> str:
    """Valor con 3 decimales si es real."""
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _delta(key: str, value: float | int, old: float | int | None) -> str:
    """Cambio coloreado: verde si mejora (para fallos, si baja)."""
    if old is None:
        return ""
    change = value - old
    if abs(change) < 1e-9:
        return "="
    better = change < 0 if "failed" in key else change > 0
    style = "green" if better else "red"
    text = f"{change:+.3f}" if isinstance(change, float) else f"{change:+d}"
    return f"[{style}]{text}[/]"


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
