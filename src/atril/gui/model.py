"""Resumen del estado para la pantalla de inicio (sin Tk: se prueba sin pantalla)."""

from dataclasses import dataclass

from atril.checks import Finding, Level
from atril.knowledge import PlanState
from atril.ops.knowledge import KbStatus
from atril.ops.service import Section

_SEVERITY = {Level.OK: 0, Level.INFO: 1, Level.WARNING: 2, Level.ERROR: 3}


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


def overall(rows: list[Row]) -> tuple[Level, str]:
    """Estado general y frase para el usuario."""
    levels = {row.level for row in rows}
    if Level.ERROR in levels:
        return Level.ERROR, "Hay problemas que impiden usar atril con normalidad"
    if Level.WARNING in levels:
        return Level.WARNING, "Atril funciona, con avisos que conviene revisar"
    return Level.OK, "Atril está listo"


INDEX_LABELS = {
    PlanState.INDEXED: ("indexada", Level.OK),
    PlanState.NEW: ("por indexar", Level.INFO),
    PlanState.CHANGED: ("cambiada: reindexar", Level.WARNING),
    PlanState.MISSING: ("sin fichero", Level.WARNING),
    PlanState.REMOVED: ("retirada: reindexar", Level.WARNING),
}
"""Texto y nivel de cada estado de indexado, para el alumno."""


@dataclass(frozen=True, slots=True)
class SourceRow:
    """Una fuente en la tabla del temario."""

    source_id: str
    kb_id: str
    file: str
    state: str
    level: Level


def source_rows(statuses: list[KbStatus]) -> list[SourceRow]:
    """Filas de la tabla de fuentes: una por fuente y KB, en orden."""
    rows = []
    for status in statuses:
        for item in status.items:
            label, level = INDEX_LABELS[item.state]
            row = SourceRow(item.source_id, status.kb.id, item.file, label, level)
            rows.append(row)
    return rows


def actions_needed(statuses: list[KbStatus]) -> tuple[bool, list[str]]:
    """Si hay algo por indexar y qué KB hay que reindexar."""
    new = any(status.count(PlanState.NEW) for status in statuses)
    return new, [status.kb.id for status in statuses if status.needs_reindex]
