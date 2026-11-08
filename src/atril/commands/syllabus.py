"""Comandos de temarios y fuentes: ``atril temario ...`` y ``atril fuentes ...``."""

from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from atril.checks import info, ok, warning
from atril.commands._common import (
    console,
    fail,
    get_station,
    get_syllabus,
    load_or_fail,
    reporter,
    show,
    success,
)
from atril.config import ConfigError, Syllabus, load_syllabi
from atril.errors import AtrilError
from atril.ops import sources as source_ops
from atril.ops import syllabus as operations
from atril.sources import Outcome, Result, SourceManager

syllabus_app = typer.Typer(
    help="Temarios de la estación.", no_args_is_help=True, rich_markup_mode="rich"
)
sources_app = typer.Typer(
    help="Fuentes de un temario: descarga y comprobación de versiones.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

SyllabusId = Annotated[
    str,
    typer.Argument(metavar="TEMARIO", help="Id del temario (nombre de su carpeta)."),
]
SourceIds = Annotated[
    list[str] | None,
    typer.Argument(metavar="FUENTES", help="Ids de fuente; por defecto, todas."),
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
    for column in ("KB", "Fuentes", "Presentes", "Manuales", "Faltan"):
        table.add_column(column, justify="right")
    for syllabus in syllabi:
        manager = load_or_fail(lambda s=syllabus: SourceManager(s))
        states = [manager.local_state(source) for source in syllabus.sources]
        manual = states.count("manual")
        missing = states.count("falta")
        table.add_row(
            syllabus.id,
            escape(syllabus.name),
            str(len(syllabus.knowledge_bases)),
            str(len(states)),
            str(len(states) - manual - missing),
            str(manual),
            f"[yellow]{missing}[/]" if missing else "0",
        )
    console.print(table)
    show(warning(message) for message in warnings)


@syllabus_app.command("crear")
def create_syllabus(
    ctx: typer.Context,
    name: Annotated[
        str, typer.Argument(metavar="NOMBRE", help="Nombre visible del temario.")
    ],
    syllabus_id: Annotated[
        str | None,
        typer.Option("--id", help="Id (carpeta); por defecto, sale del nombre."),
    ] = None,
) -> None:
    """Crea un temario vacío con una KB que recoge todas sus fuentes.

    Genera [bold]temarios/<id>/temario.toml[/], [bold]prompt.md[/] y la carpeta
    [bold]fuentes/[/]. Después, añade fuentes con [bold]atril fuentes añadir[/].
    """
    try:
        syllabus = operations.create(get_station(ctx), name, syllabus_id)
    except (AtrilError, ConfigError) as exc:
        fail(str(exc))
    success(f"Temario {syllabus.id} creado en {syllabus.root}.")
    console.print(
        f"Añade fuentes con: atril fuentes añadir {syllabus.id} <fichero.pdf | url>"
    )


@syllabus_app.command("cobertura")
def coverage(ctx: typer.Context, syllabus_id: SyllabusId) -> None:
    """Muestra, KB a KB, qué fuentes están en disco y cuándo se comprobaron."""
    syllabus = get_syllabus(ctx, syllabus_id)
    manager = load_or_fail(lambda: SourceManager(syllabus))
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
    syllabus = get_syllabus(ctx, syllabus_id)
    try:
        results = source_ops.download(syllabus, reporter, source_ids)
    except AtrilError as exc:
        fail(str(exc))
    _report(syllabus, results, "Descarga")


@sources_app.command("añadir")
def add_source(
    ctx: typer.Context,
    syllabus_id: SyllabusId,
    origin: Annotated[
        str,
        typer.Argument(metavar="ORIGEN", help="Fichero PDF o URL http(s) de un PDF."),
    ],
    source_id: Annotated[
        str | None,
        typer.Option("--id", help="Id; por defecto, se deduce."),
    ] = None,
    title: Annotated[str | None, typer.Option("--titulo", help="Título.")] = None,
    kb_id: Annotated[
        str | None,
        typer.Option("--kb", help="KB, si el temario tiene varias."),
    ] = None,
) -> None:
    """Añade una fuente PDF: copia un fichero local o declara una URL.

    El fichero se copia a [bold]fuentes/<kb>/[/]; una URL se descarga después con
    [bold]atril fuentes descargar[/]. [bold]temario.toml[/] conserva sus comentarios.
    """
    syllabus = get_syllabus(ctx, syllabus_id)
    try:
        source = operations.add_source(
            syllabus, origin, source_id=source_id, title=title, kb_id=kb_id
        )
    except AtrilError as exc:
        fail(str(exc))
    kb = syllabus.knowledge_bases[0].id if kb_id is None else kb_id
    findings = [ok(f"Fuente {source.id} añadida a la KB {kb}.")]
    if source.url:
        findings.append(
            info(f"Descárgala con: atril fuentes descargar {syllabus.id} {source.id}")
        )
    findings.append(info(f"Para indexarla: atril kb indexar {syllabus.id} {kb}"))
    show(findings)


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
    syllabus = get_syllabus(ctx, syllabus_id)
    try:
        results, skipped = source_ops.check(
            syllabus, reporter, source_ids, check_all=check_all
        )
    except AtrilError as exc:
        fail(str(exc))
    if skipped:
        show(
            [info(f"{skipped} fuentes no tocan todavía (usa --todas para forzarlas).")]
        )
    _report(syllabus, results, "Comprobación")


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

    if changed := source_ops.changed_kbs(syllabus, results):
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
