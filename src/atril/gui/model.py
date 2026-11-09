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
from atril.config.station import Station
from atril.deeptutor import Assistant
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
    """``deeptutor``, ``ollama``, ``python``, ``uv``, ``node``, ``npm``, ``git`` o
    ``asistente``."""
    name: str
    logo: str | None
    """Logotipo de ``recursos/marcas`` (``None``: icono genérico)."""
    state: str
    """Una sola línea."""
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
    """``python``, ``uv``, ``node``, ``npm``, ``git`` y ``claude``: si están."""
    assistant: Assistant | None
    """Modelo de chat activo (catálogo de DeepTutor o ``[deeptutor.llm]``)."""
    ollama_required: bool
    """``atril.toml`` declara ``[ollama]`` (indexado)."""
    pending: list[Finding] = field(default_factory=list)
    """Avisos de DeepTutor (parches pendientes...)."""

    @property
    def deeptutor_running(self) -> bool:
        """DeepTutor responde por completo."""
        return self.backend_up and self.frontend_up


TOOLS = {
    "python": ("Python", "python"),
    "uv": ("uv", "uv"),
    "node": ("Node.js", "nodejs"),
    "npm": ("npm", "npm"),
    "git": ("Git", "git"),
}
"""Herramientas de instalación: nombre visible y logotipo."""

ORDER = ("deeptutor", "ollama", "python", "uv", "node", "npm", "git", "asistente")
"""Orden de las tarjetas en Inicio, de dos en dos."""

WEBSITES = {
    "deeptutor": "https://github.com/HKUDS/DeepTutor",
    "ollama": "https://ollama.com",
    "python": "https://www.python.org",
    "uv": "https://docs.astral.sh/uv/",
    "node": "https://nodejs.org",
    "npm": "https://www.npmjs.com",
    "git": "https://git-scm.com",
}
"""Web de cada herramienta (al pulsar su logotipo)."""


def tool_cards(facts: Facts) -> list[ToolCard]:
    """Las ocho herramientas de Inicio, en :data:`ORDER`, con su estado y acción.

    Examples:
        >>> facts = Facts(True, True, True, True, False, False, (), {}, None, True)
        >>> [(c.key, c.state, c.action.value) for c in tool_cards(facts)][:2]
        [('deeptutor', 'En marcha', 'Parar'), ('ollama', 'Parado', 'Arrancar')]
    """
    cards = {
        "deeptutor": _deeptutor_card(facts),
        "ollama": _ollama_card(facts),
        "asistente": assistant_card(facts),
    }
    for key, (name, logo) in TOOLS.items():
        if facts.tools.get(key):
            cards[key] = ToolCard(key, name, logo, "Instalado", Level.OK)
        else:
            cards[key] = ToolCard(
                key, name, logo, "No instalado", Level.ERROR, Action.INSTALL
            )
    return [cards[key] for key in ORDER]


def _deeptutor_card(facts: Facts) -> ToolCard:
    """DeepTutor: instalar, arrancar o parar."""

    def card(state: str, level: Level, action: Action) -> ToolCard:
        return ToolCard("deeptutor", "DeepTutor", "deeptutor", state, level, action)

    if not facts.deeptutor_installed:
        return card("No instalado", Level.ERROR, Action.INSTALL)
    if facts.deeptutor_running:
        return card("En marcha", Level.OK, Action.STOP)
    if facts.backend_up or facts.frontend_up:
        return card("Arranque incompleto", Level.WARNING, Action.STOP)
    return card("Parado", Level.INFO, Action.START)


def _ollama_card(facts: Facts) -> ToolCard:
    """Ollama: instalar, arrancar, parar (solo el que abrió atril) o nada."""

    def card(state: str, level: Level, action: Action = Action.NONE) -> ToolCard:
        return ToolCard("ollama", "Ollama", "ollama", state, level, action)

    if not facts.ollama_installed:
        if facts.ollama_required:
            return card("No instalado", Level.WARNING, Action.INSTALL)
        return card("No instalado (opcional)", Level.INFO, Action.INSTALL)
    if not facts.ollama_running:
        return card("Parado", Level.INFO, Action.START)
    return card(
        "En marcha", Level.OK, Action.STOP if facts.ollama_ours else Action.NONE
    )


PROVIDERS = {
    "claude_code": "Claude Code",
    "anthropic": "Claude",
    "openai": "GPT",
    "azure_openai": "GPT (Azure)",
    "gemini": "Gemini",
    "google": "Gemini",
    "deepseek": "DeepSeek",
    "ollama": "Ollama",
    "openrouter": "OpenRouter",
}
"""Nombre visible de los proveedores de chat más comunes."""


def assistant_card(facts: Facts) -> ToolCard:
    """Asistente de DeepTutor y si está accesible.

    ``claude_code`` necesita el programa ``claude``; un modelo de Ollama, estar
    descargado; un proveedor en la nube, su clave en DeepTutor.

    Examples:
        >>> facts = Facts(True, False, False, True, True, True, (), {}, None, False)
        >>> assistant_card(facts).state
        'Sin configurar en DeepTutor'
        >>> facts = Facts(
        ...     True, False, False, True, True, True, (), {},
        ...     Assistant("gemini", "gemini-2.5-pro", False), False,
        ... )
        >>> assistant_card(facts).state
        'Gemini sin clave'
    """
    assistant = facts.assistant

    def card(state: str, level: Level, action: Action = Action.NONE) -> ToolCard:
        logo = "ollama" if assistant and assistant.provider == "ollama" else None
        return ToolCard("asistente", "Asistente", logo, state, level, action)

    if assistant is None or not assistant.provider:
        return card("Sin configurar en DeepTutor", Level.WARNING)
    label = PROVIDERS.get(assistant.provider, assistant.provider)
    if assistant.provider == "claude_code":
        if facts.tools.get("claude"):
            return card("Claude Code disponible", Level.OK)
        return card("Claude Code no instalado", Level.ERROR, Action.INSTALL)
    if assistant.provider == "ollama":
        name = assistant.model.removeprefix("ollama/")
        if any(_same_model(name, model) for model in facts.ollama_models):
            return card(f"{name} disponible", Level.OK)
        if not facts.ollama_running:
            return card(f"{name} (Ollama parado)", Level.INFO)
        return card(f"{name} sin descargar", Level.WARNING, Action.PULL)
    if assistant.has_key:
        return card(f"{label} con clave", Level.OK)
    return card(f"{label} sin clave", Level.ERROR)


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
    missing = [name for key, (name, _) in TOOLS.items() if not facts.tools.get(key)]
    if missing:
        return (
            Level.ERROR,
            OVERALL[Level.ERROR][0],
            f"Falta {', '.join(missing)}: instálalo abajo.",
        )
    # ``pending`` son los parches: frase corta (cabe en una línea en Inicio).
    if any(f.level is Level.ERROR for f in facts.pending):
        return (
            Level.WARNING,
            OVERALL[Level.WARNING][0],
            "Un parche ya no encaja con DeepTutor: revísalo en Ajustes.",
        )
    if any(f.level is Level.WARNING for f in facts.pending):
        return (
            Level.WARNING,
            OVERALL[Level.WARNING][0],
            "Hay parches pendientes: se aplican al arrancar.",
        )
    level = Level.OK if facts.deeptutor_running else Level.INFO
    return level, *OVERALL[level]


def service_states(facts: Facts) -> dict[str, tuple[Level, str]]:
    """Estado de DeepTutor y Ollama para el pie de ventana."""
    cards = {card.key: card for card in tool_cards(facts)[:2]}
    return {
        "DeepTutor": (cards["deeptutor"].level, cards["deeptutor"].state),
        "Ollama": (cards["ollama"].level, cards["ollama"].state),
    }


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


type SortKey = tuple[str | int | float, ...]
"""Claves de ordenación de una fila, una por columna."""


def sort_order(
    keys: dict[str, SortKey], column: int, descending: bool, tie: int = 0
) -> list[str]:
    """Filas ordenadas por ``column``; los empates, por ``tie`` en orden ascendente.

    Examples:
        >>> keys = {"a": ("ley", 3), "b": ("decreto", 3), "c": ("orden", 1)}
        >>> sort_order(keys, 1, descending=False)
        ['c', 'b', 'a']
        >>> sort_order(keys, 1, descending=True)
        ['b', 'a', 'c']
    """
    by_tie = sorted(keys, key=lambda item: keys[item][tie])
    return sorted(by_tie, key=lambda item: keys[item][column], reverse=descending)


def fold(text: str) -> str:
    """Texto para ordenar o buscar: minúsculas y sin tildes.

    Examples:
        >>> fold("Óptica")
        'optica'
    """
    return _fold(text)


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


# --- área de notificación ---------------------------------------------------------


class CloseAction(StrEnum):
    """Qué hace la ventana al pulsar cerrar."""

    HIDE = "ocultar"
    """Al área de notificación: DeepTutor sigue en marcha."""
    WAIT = "esperar"
    """Hay una operación: se pide que pare y se cierra al acabar."""
    ASK_STOP = "preguntar"
    """Sin área de notificación y DeepTutor en marcha: ¿pararlo?"""
    QUIT = "salir"


def close_action(*, tray: bool, deeptutor_up: bool, busy: bool) -> CloseAction:
    """Decide qué hacer al cerrar la ventana.

    Con DeepTutor en marcha, la ventana se oculta en el área de notificación
    (si la hay), también con una operación en curso, que sigue. Sin DeepTutor,
    atril se cierra del todo, como siempre.

    Examples:
        >>> close_action(tray=True, deeptutor_up=True, busy=True)
        <CloseAction.HIDE: 'ocultar'>
        >>> close_action(tray=True, deeptutor_up=False, busy=False)
        <CloseAction.QUIT: 'salir'>
    """
    if tray and deeptutor_up:
        return CloseAction.HIDE
    if busy:
        return CloseAction.WAIT
    if deeptutor_up:
        return CloseAction.ASK_STOP
    return CloseAction.QUIT


class TrayCommand(StrEnum):
    """Órdenes del menú del icono (y de una segunda instancia: mostrar)."""

    SHOW = "mostrar"
    OPEN = "abrir"
    TOGGLE = "arrancar-parar"
    BACKUP = "backup"
    ACTIVITY = "actividad"
    QUIT = "salir"


@dataclass(frozen=True, slots=True)
class MenuItem:
    """Entrada del menú del icono."""

    command: TrayCommand
    text: str
    enabled: bool = True
    default: bool = False
    """En negrita: la que hace el clic en el icono."""


type TrayMenu = tuple[MenuItem | None, ...]
"""Menú del icono; ``None`` es un separador."""


def tray_menu(*, deeptutor_up: bool, busy: bool) -> TrayMenu:
    """Menú del icono según el estado de DeepTutor y si hay una operación.

    Examples:
        >>> [i.text for i in tray_menu(deeptutor_up=True, busy=False) if i][2]
        'Parar DeepTutor'
    """
    return (
        MenuItem(TrayCommand.SHOW, "Mostrar atril", default=True),
        MenuItem(TrayCommand.OPEN, "Abrir DeepTutor", enabled=deeptutor_up),
        None,
        MenuItem(
            TrayCommand.TOGGLE,
            "Parar DeepTutor" if deeptutor_up else "Arrancar DeepTutor",
            enabled=not busy,
        ),
        MenuItem(TrayCommand.BACKUP, "Hacer backup", enabled=not busy),
        MenuItem(TrayCommand.ACTIVITY, "Ver actividad"),
        None,
        MenuItem(TrayCommand.QUIT, "Salir"),
    )


TOOLTIP_LIMIT = 127
"""Caracteres que admite el texto del icono en Windows."""


def tray_tooltip(*, deeptutor_up: bool, status: str) -> str:
    """Texto al pasar el ratón por el icono: la operación en curso o DeepTutor.

    Examples:
        >>> tray_tooltip(deeptutor_up=True, status="")
        'Atril: DeepTutor en marcha'
        >>> tray_tooltip(deeptutor_up=True, status="Haciendo el backup...")
        'Atril: Haciendo el backup...'
    """
    detail = status or ("DeepTutor en marcha" if deeptutor_up else "DeepTutor parado")
    text = f"Atril: {detail}"
    return text if len(text) <= TOOLTIP_LIMIT else text[: TOOLTIP_LIMIT - 3] + "..."


@dataclass(frozen=True, slots=True)
class KbCounts:
    """Recuentos de una KB en Temarios: ``sources`` = indexed + pending + missing."""

    sources: int
    """Fuentes del temario en la KB (las retiradas ya no cuentan)."""
    indexed: int
    pending: int
    """Por indexar: nuevas o cambiadas (estas, con Reindexar)."""
    missing: int
    """Declaradas, pero sin fichero en disco."""
    removed: int
    """Retiradas del temario que siguen en la KB (hay que reindexar)."""


def kb_counts(states: list[PlanState]) -> KbCounts:
    """Recuentos coherentes a partir del estado de cada fuente de una KB.

    Examples:
        >>> S = PlanState
        >>> kb_counts([S.INDEXED, S.NEW, S.CHANGED, S.MISSING, S.REMOVED])
        KbCounts(sources=4, indexed=1, pending=2, missing=1, removed=1)
    """
    count = states.count
    return KbCounts(
        sources=len(states) - count(PlanState.REMOVED),
        indexed=count(PlanState.INDEXED),
        pending=count(PlanState.NEW) + count(PlanState.CHANGED),
        missing=count(PlanState.MISSING),
        removed=count(PlanState.REMOVED),
    )


@dataclass(frozen=True, slots=True)
class HomeStat:
    """Un dato del pie del estado general de Inicio, que lleva a su apartado."""

    title: str
    level: Level
    text: str
    view: str


STALE_BACKUP_DAYS = 7
"""Días tras los que la última copia se considera antigua."""


def syllabi_stat(data: list[SyllabusData], active: str | None) -> HomeStat:
    """Temarios: cuántos hay y cuál está activo.

    Examples:
        >>> syllabi_stat([], None).text
        'Ninguno todavía'
    """
    if not data:
        return HomeStat("Temarios", Level.INFO, "Ninguno todavía", "Temarios")
    names = {item.syllabus.id: item.syllabus.name for item in data}
    name = names.get(active or "", data[0].syllabus.name)
    count = f"{len(data)} temario" + ("s" if len(data) != 1 else "")
    return HomeStat("Temarios", Level.OK, f"{count} · activo: {name}", "Temarios")


def sources_stat(data: list[SyllabusData]) -> HomeStat:
    """Fuentes de todos los temarios y lo que les falta.

    Examples:
        >>> sources_stat([]).text
        'Ninguna todavía'
    """
    counts = [
        kb_counts([item.state for item in status.items])
        for syllabus in data
        for status in syllabus.statuses
    ]
    total = sum(c.sources for c in counts)
    pending = sum(c.pending for c in counts)
    missing = sum(c.missing for c in counts)
    if not total:
        return HomeStat("Fuentes", Level.INFO, "Ninguna todavía", "Biblioteca")
    if missing:
        return HomeStat(
            "Fuentes",
            Level.WARNING,
            f"{total} fuentes · {missing} sin fichero",
            "Biblioteca",
        )
    if pending:
        return HomeStat(
            "Fuentes",
            Level.WARNING,
            f"{total} fuentes · {pending} por indexar",
            "Temarios",
        )
    return HomeStat(
        "Fuentes", Level.OK, f"{total} fuentes · todas indexadas", "Biblioteca"
    )


def backup_stat(
    stamp: str | None, verified: bool | None, now: datetime | None = None
) -> HomeStat:
    """Último backup: cuándo y si se ha comprobado.

    Args:
        stamp: Fecha de la copia más reciente (``AAAAMMDD-HHMMSS``) o ``None``.
        verified: Resultado de su última comprobación, ``None`` si no se comprobó.
        now: Momento actual (para las pruebas).

    Examples:
        >>> backup_stat(None, None).text
        'Sin copias'
        >>> when = datetime(2026, 11, 9, 12)
        >>> backup_stat("20261108-223000", True, when).text
        'Ayer, 22:30 · verificada'
        >>> backup_stat("20261020-100000", True, when).level
        <Level.WARNING: 'aviso'>
    """
    from atril.gui.activity import when_label

    if stamp is None:
        return HomeStat("Último backup", Level.ERROR, "Sin copias", "Backups")
    moment = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
    label = when_label(moment.isoformat(), now)
    if verified is False:
        return HomeStat(
            "Último backup", Level.ERROR, f"{label} · con errores", "Backups"
        )
    if ((now or datetime.now()) - moment).days > STALE_BACKUP_DAYS:
        return HomeStat("Último backup", Level.WARNING, f"{label} · antigua", "Backups")
    if verified is None:
        return HomeStat(
            "Último backup", Level.INFO, f"{label} · sin comprobar", "Backups"
        )
    return HomeStat("Último backup", Level.OK, f"{label} · verificada", "Backups")
