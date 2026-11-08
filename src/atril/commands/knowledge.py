"""Comandos de KB: ``atril kb estado``, ``indexar``, ``reindexar`` y ``evaluar``."""

import time
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

from atril.checks import Finding, ok
from atril.commands._common import (
    console,
    fail,
    fail_error,
    find_kb,
    get_station,
    get_syllabus,
    reporter,
    show,
    success,
)
from atril.config import ConfigError, load_syllabi
from atril.config.station import Station
from atril.config.syllabus import KnowledgeBase, Syllabus
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.evaluation import (
    EvalReport,
    EvaluationError,
    previous_report,
    reports_dir,
    run_evaluation,
)
from atril.knowledge import (
    RETRY_STATES,
    PlanItem,
    PlanState,
)
from atril.ops import knowledge as operations

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
        try:
            statuses, pending = operations.status(station, syllabus, kb_id)
        except AtrilError as exc:
            fail(str(exc))
        for kb_status in statuses:
            if detail:
                _show_plan(kb_status.kb, kb_status.items)
            counts = [kb_status.count(state) for _, state in _STATE_COLUMNS]
            table.add_row(
                escape(kb_status.kb.id),
                str(len(kb_status.items) - counts[-1]),
                *(
                    _count(n, state)
                    for n, (_, state) in zip(counts, _STATE_COLUMNS, strict=True)
                ),
                _run_state(kb_status),
            )
        findings.extend(pending)
    console.print(table)
    show(findings or [ok("Todas las fuentes con fichero están indexadas.")])


def _count(number: int, state: PlanState) -> str:
    """Celda de recuento, coloreada si no es cero."""
    if not number:
        return "0"
    return f"[{_STATE_STYLE[state]}]{number}[/]"


def _run_state(kb_status: operations.KbStatus) -> str:
    """Último indexado de DeepTutor para la KB, en una celda."""
    if not kb_status.created and kb_status.run is None:
        return "[dim]sin crear[/]"
    run = kb_status.run
    if run is None:
        return "[dim]sin registro[/]"
    state = run.state
    label = escape(operations.RUN_LABELS.get(state, state) or "?")
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
    try:
        for kb_status in operations.status(station, syllabus, kb_id)[0]:
            _show_plan(kb_status.kb, kb_status.items)
        count = operations.index(station, syllabus, reporter, kb_id)
    except KeyboardInterrupt:
        console.print(
            "[yellow]Interrumpido. Vuelve a ejecutar el comando para continuar.[/]"
        )
        raise typer.Exit(130) from None
    except AtrilError as exc:
        fail_error(exc)
    success("Indexado completo." if count else "Nada que indexar.")


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
    try:
        message = operations.reindex(station, syllabus, kb, reporter)
    except KeyboardInterrupt:
        console.print("[yellow]Interrumpido. Repite el comando para continuar.[/]")
        raise typer.Exit(130) from None
    except AtrilError as exc:
        fail_error(exc)
    success(message)


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
    try:
        operations.preflight(station, reporter)
    except AtrilError as exc:
        fail(str(exc))

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


# --- reindexado ----------------------------------------------------------------


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
