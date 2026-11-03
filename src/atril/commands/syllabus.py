"""Comandos de temarios y fuentes: ``atril temario ...`` y ``atril fuentes ...``."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

import typer
from acodo.utils import get_now
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from atril.checks import info, warning
from atril.commands._common import console, fail, get_station, show
from atril.config import ConfigError, Syllabus, load_syllabi, load_syllabus
from atril.config.syllabus import Source
from atril.sources import Outcome, Result, SourceManager, is_due
from atril.sources import Progress as ProgressCallback

syllabus_app = typer.Typer(
    help="Temarios de la estación.", no_args_is_help=True, rich_markup_mode="rich"
)
sources_app = typer.Typer(
    help="Fuentes de un temario: descarga y comprobación de versiones.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

SyllabusId = Annotated[
    str, typer.Argument(help="Id del temario (nombre de su carpeta).")
]
SourceIds = Annotated[
    list[str] | None, typer.Argument(help="Ids de fuente; por defecto, todas.")
]

_OUTCOME_STYLE = {
    Outcome.DOWNLOADED: "green",
    Outcome.UPDATED: "bold yellow",
    Outcome.UNCHANGED: "green",
    Outcome.PRESENT: "dim",
    Outcome.REMOTE: "dim",
    Outcome.MANUAL: "yellow",
    Outcome.MISSING: "yellow",
    Outcome.FAILED: "bold red",
}

_STATE_STYLE = {
    "presente": "green",
    "remota": "dim",
    "falta": "yellow",
    "manual": "yellow",
    "sin registro": "yellow",
    "modificada": "bold red",
}


@syllabus_app.command("lista")
def list_syllabi(ctx: typer.Context) -> None:
    """Lista los temarios con sus KB y el estado de sus fuentes."""
    station = get_station(ctx)
    try:
        syllabi, warnings = load_syllabi(station.syllabi_dir)
    except ConfigError as exc:
        fail(str(exc))
    if not syllabi:
        show([info(f"No hay temarios en {station.syllabi_dir}.")])
        return

    table = Table("Temario", "Nombre", title="Temarios", title_justify="left")
    for column in ("KB", "Fuentes", "Presentes", "Faltan"):
        table.add_column(column, justify="right")
    for syllabus in syllabi:
        manager = SourceManager(syllabus)
        states = [manager.local_state(source) for source in syllabus.sources]
        missing = sum(state in {"falta", "manual"} for state in states)
        table.add_row(
            syllabus.id,
            escape(syllabus.name),
            str(len(syllabus.knowledge_bases)),
            str(len(states)),
            str(sum(state != "falta" for state in states)),
            f"[yellow]{missing}[/]" if missing else "0",
        )
    console.print(table)
    show(warning(message) for message in warnings)


@syllabus_app.command("cobertura")
def coverage(ctx: typer.Context, syllabus_id: SyllabusId) -> None:
    """Muestra, KB a KB, qué fuentes están en disco y cuándo se comprobaron."""
    syllabus = _syllabus(ctx, syllabus_id)
    manager = SourceManager(syllabus)
    for kb in syllabus.knowledge_bases:
        kind = "vinculante" if kb.binding else "no vinculante"
        table = Table(
            "Fuente",
            "Tipo",
            "Fichero",
            "Estado",
            "Comprobar",
            "Última comprobación",
            title=f"KB [bold]{escape(kb.id)}[/] ({kind})",
            title_justify="left",
        )
        for source in syllabus.sources_of(kb):
            state = manager.local_state(source)
            record = manager.registry.get(source.id)
            path = syllabus.source_path(source)
            table.add_row(
                escape(source.id),
                source.kind.value,
                escape(str(path.relative_to(syllabus.sources_dir))) if path else "—",
                f"[{_STATE_STYLE.get(state, '')}]{state}[/]",
                source.check.value,
                record.checked_at[:10] if record else "—",
            )
        console.print(table)
    show(warning(message) for message in syllabus.warnings)


@sources_app.command("descargar")
def download_sources(
    ctx: typer.Context, syllabus_id: SyllabusId, source_ids: SourceIds = None
) -> None:
    """Descarga las fuentes que faltan (no toca las que ya están en disco)."""
    syllabus = _syllabus(ctx, syllabus_id)
    manager = SourceManager(syllabus)
    results = []
    with _progress() as progress:
        for source in _select(syllabus, source_ids):
            with _task(progress, source) as callback:
                results.append(manager.fetch(source, callback))
            manager.registry.save()
    _report(syllabus, results, "Descarga")


@sources_app.command("comprobar")
def check_sources(
    ctx: typer.Context,
    syllabus_id: SyllabusId,
    source_ids: SourceIds = None,
    check_all: Annotated[
        bool,
        typer.Option(
            "--todas", help="Comprueba todas las fuentes con url, toque o no."
        ),
    ] = False,
) -> None:
    """Busca versiones nuevas de las fuentes y guarda la anterior en el histórico.

    Por defecto revisa solo las que tocan según su frecuencia ([bold]comprobar[/]).
    """
    syllabus = _syllabus(ctx, syllabus_id)
    manager = SourceManager(syllabus)
    now = get_now()
    candidates = [source for source in _select(syllabus, source_ids) if source.url]
    explicit = bool(source_ids) or check_all
    due = [
        s for s in candidates if explicit or is_due(s, manager.registry.get(s.id), now)
    ]
    skipped = len(candidates) - len(due)

    results = []
    with _progress() as progress:
        for source in due:
            with _task(progress, source) as callback:
                results.append(manager.check(source, callback))
            manager.registry.save()
    if skipped:
        show(
            [info(f"{skipped} fuentes no tocan todavía (usa --todas para forzarlas).")]
        )
    _report(syllabus, results, "Comprobación")


def _syllabus(ctx: typer.Context, syllabus_id: str) -> Syllabus:
    """Carga un temario por id; termina con error si no existe o no es válido."""
    station = get_station(ctx)
    root = station.syllabi_dir / syllabus_id
    if not (root / "temario.toml").is_file():
        found = sorted(
            p.parent.name for p in station.syllabi_dir.glob("*/temario.toml")
        )
        names = ", ".join(found) or "ninguno"
        fail(f"no existe el temario {syllabus_id!r} (disponibles: {names}).")
    try:
        return load_syllabus(root)
    except ConfigError as exc:
        fail(str(exc))


def _select(syllabus: Syllabus, source_ids: list[str] | None) -> list[Source]:
    """Fuentes pedidas, en el orden del temario; termina si algún id no existe."""
    if not source_ids:
        return list(syllabus.sources)
    known = {source.id: source for source in syllabus.sources}
    unknown = [item for item in source_ids if item not in known]
    if unknown:
        fail(f"fuentes desconocidas en {syllabus.id}: {', '.join(unknown)}.")
    return [known[item] for item in source_ids]


def _progress() -> Progress:
    """Barra de progreso de descargas (se oculta al terminar cada una)."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
        transient=True,
    )


@contextmanager
def _task(progress: Progress, source: Source) -> Generator[ProgressCallback]:
    """Tarea de progreso para una fuente; devuelve la función de avance."""
    task = progress.add_task(escape(source.id), total=None)

    def update(done: int, total: int | None) -> None:
        progress.update(task, completed=done, total=total)

    try:
        yield update
    finally:
        progress.remove_task(task)


def _report(syllabus: Syllabus, results: list[Result], title: str) -> None:
    """Tabla de resultados; avisa de KB a reindexar y termina con 1 si hubo errores."""
    if results:
        table = Table(
            "Fuente", "KB", "Resultado", "Detalle", title=title, title_justify="left"
        )
        for result in results:
            style = _OUTCOME_STYLE.get(result.outcome, "")
            table.add_row(
                escape(result.source.id),
                escape(syllabus.kb_of(result.source).id),
                f"[{style}]{result.outcome.value}[/]",
                escape(result.detail),
            )
        console.print(table)

    changed = sorted(
        {syllabus.kb_of(r.source).id for r in results if r.outcome is Outcome.UPDATED}
    )
    if changed:
        show(
            [
                warning(
                    f"Fuentes nuevas en: {', '.join(changed)}. Reindexa esas KB para "
                    "que DeepTutor use la versión actual."
                )
            ]
        )
    if any(result.outcome is Outcome.FAILED for result in results):
        fail("alguna fuente no se ha podido descargar.")
