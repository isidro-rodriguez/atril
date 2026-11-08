"""Lógica de presentación sin Tk: se prueba sin pantalla.

Convierte el estado de la estación en textos y acciones para el alumno, sin
rutas ni detalles técnicos ni comandos de la consola.
"""

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from atril.checks import Finding, Level
from atril.config import Syllabus, load_syllabi
from atril.config.station import LlmConfig, Station
from atril.knowledge import PlanState
from atril.ops import knowledge as knowledge_ops
from atril.ops.knowledge import KbStatus

MONTHS = (
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
)


class Action(StrEnum):
    """Acción única de una herramienta en Inicio (el valor es el texto del botón)."""

    NONE = ""
    INSTALL = "Instalar"
    START = "Arrancar"
    STOP = "Parar"
    PULL = "Descargar"


@dataclass(frozen=True, slots=True)
class ToolCard:
    """Una herramienta en Inicio: nombre, logotipo, estado y su acción."""

    key: str
    """``deeptutor``, ``ollama``, ``git``, ``uv``, ``node`` o ``asistente``."""
    name: str
    logo: str | None
    """Logotipo de ``recursos/marcas`` (``None``: icono genérico)."""
    state: str
    level: Level
    action: Action = Action.NONE


@dataclass(frozen=True, slots=True)
class Facts:
    """Lo que se sabe de la estación para Inicio, leído en segundo plano."""

    deeptutor_installed: bool
    backend_up: bool
    frontend_up: bool
    ollama_installed: bool
    ollama_running: bool
    ollama_ours: bool
    """El Ollama en marcha lo abrió atril (solo ese se puede parar)."""
    ollama_models: tuple[str, ...]
    tools: dict[str, bool]
    """``git``, ``uv``, ``node`` y ``claude``: si están en el PATH."""
    llm: LlmConfig | None
    ollama_required: bool
    """``atril.toml`` declara ``[ollama]`` (indexado)."""
    pending: list[Finding] = field(default_factory=list)
    """Avisos de DeepTutor (parches pendientes...)."""

    @property
    def deeptutor_running(self) -> bool:
        """DeepTutor responde por completo."""
        return self.backend_up and self.frontend_up


TOOL_NAMES = {"git": "Git", "uv": "uv", "node": "Node.js"}
"""Nombre visible de las herramientas de instalación."""


def tool_cards(facts: Facts) -> list[ToolCard]:
    """Las seis herramientas de Inicio con su estado y su acción.

    Examples:
        >>> facts = Facts(True, True, True, True, False, False, (), {}, None, True)
        >>> [(c.key, c.state, c.action.value) for c in tool_cards(facts)][:2]
        [('deeptutor', 'En marcha', 'Parar'), ('ollama', 'Parado', 'Arrancar')]
    """
    return [
        _deeptutor_card(facts),
        _ollama_card(facts),
        *(
            ToolCard(
                key, name, key if key != "node" else "nodejs", "Instalado", Level.OK
            )
            if facts.tools.get(key)
            else ToolCard(
                key,
                name,
                key if key != "node" else "nodejs",
                "No instalado",
                Level.ERROR,
                Action.INSTALL,
            )
            for key, name in TOOL_NAMES.items()
        ),
        assistant_card(facts),
    ]


def _deeptutor_card(facts: Facts) -> ToolCard:
    """DeepTutor: instalar, arrancar o parar."""
    if not facts.deeptutor_installed:
        return ToolCard(
            "deeptutor",
            "DeepTutor",
            "deeptutor",
            "No instalado",
            Level.ERROR,
            Action.INSTALL,
        )
    if facts.deeptutor_running:
        return ToolCard(
            "deeptutor", "DeepTutor", "deeptutor", "En marcha", Level.OK, Action.STOP
        )
    if facts.backend_up or facts.frontend_up:
        return ToolCard(
            "deeptutor",
            "DeepTutor",
            "deeptutor",
            "Arranque incompleto",
            Level.WARNING,
            Action.STOP,
        )
    return ToolCard(
        "deeptutor", "DeepTutor", "deeptutor", "Parado", Level.INFO, Action.START
    )


def _ollama_card(facts: Facts) -> ToolCard:
    """Ollama: instalar, arrancar, parar (solo el que abrió atril) o nada."""
    optional = "" if facts.ollama_required else " (opcional)"
    if not facts.ollama_installed:
        return ToolCard(
            "ollama",
            "Ollama",
            "ollama",
            f"No instalado{optional}",
            Level.WARNING if facts.ollama_required else Level.INFO,
            Action.INSTALL,
        )
    if not facts.ollama_running:
        return ToolCard(
            "ollama", "Ollama", "ollama", "Parado", Level.INFO, Action.START
        )
    if facts.ollama_ours:
        return ToolCard(
            "ollama", "Ollama", "ollama", "En marcha", Level.OK, Action.STOP
        )
    return ToolCard(
        "ollama", "Ollama", "ollama", "En marcha (abierto aparte)", Level.OK
    )


def assistant_card(facts: Facts) -> ToolCard:
    """Asistente de DeepTutor según ``[deeptutor.llm]``.

    ``claude_code`` necesita el programa ``claude``; un modelo de Ollama, estar
    descargado. Sin ``[deeptutor.llm]`` se configura dentro de DeepTutor.

    Examples:
        >>> from atril.config.station import LlmConfig
        >>> facts = Facts(
        ...     True, False, False, True, True, True, ("qwen3:8b",), {}, None, False
        ... )
        >>> assistant_card(facts).state
        'Configurado en DeepTutor'
    """
    llm = facts.llm
    if llm is None:
        return ToolCard(
            "asistente", "Asistente", None, "Configurado en DeepTutor", Level.OK
        )
    if llm.provider == "claude_code":
        if facts.tools.get("claude"):
            return ToolCard("asistente", "Claude Code", None, "Instalado", Level.OK)
        return ToolCard(
            "asistente",
            "Claude Code",
            None,
            "No instalado",
            Level.ERROR,
            Action.INSTALL,
        )
    if llm.provider == "ollama":
        name = llm.model.removeprefix("ollama/")
        if any(_same_model(name, model) for model in facts.ollama_models):
            return ToolCard("asistente", name, "ollama", "Descargado", Level.OK)
        if not facts.ollama_running:
            return ToolCard("asistente", name, "ollama", "Ollama parado", Level.INFO)
        return ToolCard(
            "asistente", name, "ollama", "Sin descargar", Level.WARNING, Action.PULL
        )
    return ToolCard("asistente", llm.model, None, llm.provider, Level.OK)


def _same_model(wanted: str, installed: str) -> bool:
    """Mismo modelo de Ollama, con o sin ``:latest``."""
    return wanted.removesuffix(":latest") == installed.removesuffix(":latest")


OVERALL = {
    Level.OK: ("En marcha", "DeepTutor está listo para estudiar."),
    Level.INFO: ("Parado", "Arranca atril para estudiar con DeepTutor."),
    Level.WARNING: ("Con avisos", "Funciona, con avisos que conviene revisar."),
    Level.ERROR: ("Necesita atención", "Falta algo para poder usar DeepTutor."),
}
"""Por nivel: titular y frase del estado general."""


def overall(facts: Facts) -> tuple[Level, str, str]:
    """Estado general: nivel, titular y frase (la del aviso, si lo hay).

    Examples:
        >>> facts = Facts(False, False, False, True, True, True, (), {}, None, True)
        >>> overall(facts)[1:]
        ('Necesita atención', 'DeepTutor no está instalado: instálalo abajo.')
    """
    if not facts.deeptutor_installed:
        return (
            Level.ERROR,
            OVERALL[Level.ERROR][0],
            "DeepTutor no está instalado: instálalo abajo.",
        )
    missing = [TOOL_NAMES[key] for key in TOOL_NAMES if not facts.tools.get(key)]
    if missing:
        return (
            Level.ERROR,
            OVERALL[Level.ERROR][0],
            f"Falta {', '.join(missing)}: instálalo abajo.",
        )
    warnings = [f for f in facts.pending if f.level in {Level.WARNING, Level.ERROR}]
    if warnings:
        return Level.WARNING, OVERALL[Level.WARNING][0], _sentence(warnings[0].message)
    level = Level.OK if facts.deeptutor_running else Level.INFO
    return level, *OVERALL[level]


def service_states(facts: Facts) -> dict[str, tuple[Level, str]]:
    """Estado de DeepTutor y Ollama para el pie de ventana."""
    cards = {card.key: card for card in tool_cards(facts)[:2]}
    return {
        "DeepTutor": (cards["deeptutor"].level, cards["deeptutor"].state),
        "Ollama": (
            cards["ollama"].level,
            cards["ollama"].state.removesuffix(" (abierto aparte)"),
        ),
    }


def _sentence(text: str) -> str:
    """Primera letra en mayúscula y punto final."""
    text = text[:1].upper() + text[1:]
    return text if text.endswith(".") else f"{text}."


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


def choose_syllabus(ids: list[str], remembered: str | None) -> str | None:
    """Temario activo: el recordado si sigue existiendo, si no el primero.

    Examples:
        >>> choose_syllabus(["a", "b"], "b"), choose_syllabus(["a"], "x")
        ('b', 'a')
        >>> choose_syllabus([], "x") is None
        True
    """
    if remembered in ids:
        return remembered
    return ids[0] if ids else None


@dataclass(frozen=True, slots=True)
class SourceRow:
    """Una fuente en la Biblioteca."""

    source_id: str
    title: str
    kb_id: str
    file: str
    state: str
    level: Level


def source_rows(data: SyllabusData) -> list[SourceRow]:
    """Fuentes de un temario, en orden."""
    rows = []
    for status in data.statuses:
        for plan in status.items:
            label, level = INDEX_LABELS[plan.state]
            title = plan.source.title if plan.source and plan.source.title else ""
            rows.append(
                SourceRow(
                    plan.source_id,
                    title or plan.source_id,
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


def filter_rows(rows: list[SourceRow], query: str = "") -> list[SourceRow]:
    """Filas que contienen ``query`` (sin tildes ni mayúsculas).

    Examples:
        >>> row = SourceRow("ley-39", "Ley 39/2015", "kb", "ley.pdf", "", Level.OK)
        >>> [r.source_id for r in filter_rows([row], "LEY 39")]
        ['ley-39']
        >>> filter_rows([row], "decreto")
        []
    """
    wanted = _fold(query.strip())
    return [
        row
        for row in rows
        if not wanted
        or wanted in _fold(f"{row.title} {row.source_id} {row.file} {row.kb_id}")
    ]


def actions_needed(statuses: list[KbStatus]) -> tuple[bool, list[str]]:
    """Si hay algo por indexar y qué KB hay que reindexar."""
    new = any(status.count(PlanState.NEW) for status in statuses)
    return new, [status.kb.id for status in statuses if status.needs_reindex]


def archive_label(stamp: str) -> str:
    """Fecha de un backup a partir de su nombre: «8 nov 2026, 09:00».

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


def size_label(size: int) -> str:
    """Tamaño en lenguaje llano: «512 B», «3,4 MB», «1,2 GB».

    Examples:
        >>> size_label(3_400_000), size_label(512)
        ('3,4 MB', '512 B')
    """
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            text = f"{value:.0f}" if unit == "B" else f"{value:.1f}".replace(".", ",")
            return f"{text} {unit}"
        value /= 1000
    return f"{size} B"
