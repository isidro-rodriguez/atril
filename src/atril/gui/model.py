"""Resumen del estado para la pantalla de inicio (sin Tk: se prueba sin pantalla)."""

from dataclasses import dataclass

from atril.checks import Finding, Level
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
