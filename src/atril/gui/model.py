"""Lógica de presentación sin Tk: se prueba sin pantalla.

Convierte resultados de :mod:`atril.ops` en filas y textos para el alumno: sin
rutas ni detalles técnicos (esos van a Diagnóstico).
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime

from atril.checks import Finding, Level
from atril.config import Syllabus, load_syllabi
from atril.config.station import Station
from atril.knowledge import PlanState
from atril.ops import knowledge as knowledge_ops
from atril.ops.installation import Tool
from atril.ops.knowledge import KbStatus
from atril.ops.service import Section

_SEVERITY = {Level.OK: 0, Level.INFO: 1, Level.WARNING: 2, Level.ERROR: 3}

MONTHS = [
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
]


@dataclass(frozen=True, slots=True)
class Row:
    """Una línea del resumen: sección, nivel más grave y su mensaje."""

    title: str
    level: Level
    message: str


def worst(findings: list[Finding]) -> Finding | None:
    """Comprobación más grave (la primera de su nivel)."""
    if not findings:
        return None
    return max(findings, key=lambda finding: _SEVERITY[finding.level])


def summarize(sections: list[Section]) -> list[Row]:
    """Una fila por sección con su comprobación más grave.

    En DeepTutor se prefiere el estado del servicio («En marcha», «Parado») a la
    línea de instalación cuando ambas están bien.
    """
    rows = []
    for title, findings in sections:
        chosen = worst(findings)
        if chosen is None:
            continue
        if title == "DeepTutor" and chosen.level is Level.OK and len(findings) > 1:
            chosen = findings[1]
        rows.append(Row(title, chosen.level, chosen.message))
    return rows


OVERALL = {
    Level.OK: ("Preparado", "Todo funciona correctamente", "Operativa"),
    Level.WARNING: (
        "Con avisos",
        "Atril funciona, con avisos que conviene revisar",
        "Con avisos",
    ),
    Level.ERROR: (
        "Necesita atención",
        "Hay problemas que impiden usar atril con normalidad",
        "Atención",
    ),
}
"""Por nivel: titular, frase y palabra del indicador de la cabecera."""


def overall(rows: list[Row]) -> tuple[Level, str, str]:
    """Estado general: nivel, titular y frase para el alumno."""
    levels = {row.level for row in rows}
    level = (
        Level.ERROR
        if Level.ERROR in levels
        else Level.WARNING
        if Level.WARNING in levels
        else Level.OK
    )
    headline, sentence, _ = OVERALL[level]
    return level, headline, sentence


def status_word(level: Level) -> str:
    """Palabra del indicador de la cabecera («Operativa», «Con avisos»...)."""
    return OVERALL.get(level, OVERALL[Level.OK])[2]


INDEX_LABELS = {
    PlanState.INDEXED: ("Indexada", Level.OK),
    PlanState.NEW: ("Por indexar", Level.INFO),
    PlanState.CHANGED: ("Cambiada: reindexar", Level.WARNING),
    PlanState.MISSING: ("Sin fichero", Level.WARNING),
    PlanState.REMOVED: ("Retirada: reindexar", Level.WARNING),
}
"""Texto y nivel de cada estado de indexado, para el alumno."""


@dataclass(frozen=True, slots=True)
class SyllabusData:
    """Un temario con el estado de sus KB y lo que tiene pendiente."""

    syllabus: Syllabus
    statuses: list[KbStatus]
    pending: list[Finding]


def load_all(station: Station) -> list[SyllabusData]:
    """Temarios de la estación con su estado (lee ficheros y calcula hashes)."""
    syllabi, _ = load_syllabi(station.syllabi_dir)
    return [SyllabusData(s, *knowledge_ops.status(station, s)) for s in syllabi]


@dataclass(frozen=True, slots=True)
class SourceRow:
    """Una fuente en la Biblioteca."""

    source_id: str
    title: str
    syllabus_id: str
    syllabus_name: str
    kb_id: str
    file: str
    state: str
    level: Level


def source_rows(data: list[SyllabusData]) -> list[SourceRow]:
    """Todas las fuentes de todos los temarios, en orden."""
    rows = []
    for item in data:
        for status in item.statuses:
            for plan in status.items:
                label, level = INDEX_LABELS[plan.state]
                title = plan.source.title if plan.source and plan.source.title else ""
                rows.append(
                    SourceRow(
                        plan.source_id,
                        title or plan.source_id,
                        item.syllabus.id,
                        item.syllabus.name,
                        status.kb.id,
                        plan.file,
                        label,
                        level,
                    )
                )
    return rows


def _fold(text: str) -> str:
    """Minúsculas sin tildes, para buscar."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def filter_rows(
    rows: list[SourceRow], query: str = "", syllabus_id: str | None = None
) -> list[SourceRow]:
    """Filas que contienen ``query`` (sin tildes ni mayúsculas) y son del temario.

    Examples:
        >>> row = SourceRow(
        ...     "ley-39", "Ley 39/2015", "n", "N", "kb", "ley.pdf", "", Level.OK
        ... )
        >>> [r.source_id for r in filter_rows([row], "LEY 39")]
        ['ley-39']
        >>> filter_rows([row], "decreto")
        []
    """
    wanted = _fold(query.strip())
    return [
        row
        for row in rows
        if (syllabus_id is None or row.syllabus_id == syllabus_id)
        and (
            not wanted
            or wanted in _fold(f"{row.title} {row.source_id} {row.file} {row.kb_id}")
        )
    ]


def actions_needed(statuses: list[KbStatus]) -> tuple[bool, list[str]]:
    """Si hay algo por indexar y qué KB hay que reindexar."""
    new = any(status.count(PlanState.NEW) for status in statuses)
    return new, [status.kb.id for status in statuses if status.needs_reindex]


TOOL_LABELS = {
    "git": "Git",
    "uv": "uv (Python)",
    "node": "Node.js",
    "npm": "npm",
    "ollama": "Ollama",
    "claude": "Claude Code",
}
"""Nombre visible de cada herramienta."""


def tool_rows(tools: list[Tool]) -> list[tuple[str, str, Level]]:
    """Herramientas en lenguaje llano: nombre, estado y nivel (sin rutas)."""
    rows = []
    for tool in tools:
        label = TOOL_LABELS.get(tool.name, tool.name)
        if tool.path:
            rows.append((label, "Disponible", Level.OK))
        elif tool.required:
            rows.append((label, "No instalado", Level.ERROR))
        else:
            rows.append((label, "No instalado (opcional)", Level.WARNING))
    return rows


def archive_label(stamp: str) -> str:
    """Fecha de una copia a partir de su nombre: «8 nov 2026, 09:00».

    Examples:
        >>> archive_label("20261108-090000")
        '8 nov 2026, 09:00'
        >>> archive_label("20261108-090000-2")
        '8 nov 2026, 09:00'
    """
    try:
        moment = datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return stamp
    month = MONTHS[moment.month - 1]
    return f"{moment.day} {month} {moment.year}, {moment:%H:%M}"


def ago_label(timestamp: float, now: float) -> str:
    """Antigüedad en lenguaje llano: «Hoy», «Ayer», «Hace 3 días», «Hace 2 semanas».

    Examples:
        >>> ago_label(0, 3600)
        'Hoy'
        >>> ago_label(0, 86400 * 9)
        'Hace 1 semana'
    """
    days = int((now - timestamp) // 86400)
    if days <= 0:
        return "Hoy"
    if days == 1:
        return "Ayer"
    if days < 7:
        return f"Hace {days} días"
    weeks = days // 7
    if weeks < 5:
        return f"Hace {weeks} semana{'s' if weeks > 1 else ''}"
    return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y")
