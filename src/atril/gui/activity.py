"""Actividad de la GUI: un evento por operación, guardado en la estación.

Cada operación que lanza la ventana (copia, indexado, arranque...) es un
:class:`Event` con título, resumen y nivel; las comprobaciones que produce quedan
como detalle técnico. El panel lateral muestra el resumen y «Ver todo» el
detalle. Se guarda en ``data/atril/actividad.jsonl`` (una línea por evento
terminado) para conservar el historial entre sesiones. Sin Tk: se prueba sin
pantalla.
"""

import contextlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from atril.checks import Finding, Level

MAX_EVENTS = 500
"""Eventos que se conservan en el fichero."""

_SEVERITY = {Level.OK: 0, Level.INFO: 1, Level.WARNING: 2, Level.ERROR: 3}


@dataclass(slots=True)
class Event:
    """Una operación de la ventana."""

    title: str
    category: str = "general"
    level: Level = Level.INFO
    summary: str = "En curso…"
    detail: list[tuple[str, str]] = field(default_factory=list)
    """Comprobaciones producidas: (nivel, mensaje)."""
    when: str = field(default_factory=lambda: _now())
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    running: bool = True

    def add(self, findings: list[Finding]) -> None:
        """Añade comprobaciones al detalle."""
        self.detail.extend((f.level.value, f.message) for f in findings)

    def finish(self, level: Level | None = None, summary: str | None = None) -> None:
        """Cierra el evento; sin datos, resume a partir de su detalle."""
        self.running = False
        worst = _worst(self.detail)
        self.level = level if level is not None else (worst or Level.OK)
        if summary is not None:
            self.summary = summary
        elif worst in {Level.WARNING, Level.ERROR}:
            self.summary = next(m for v, m in self.detail if Level(v) is worst)
        elif self.detail:
            self.summary = self.detail[-1][1]
        else:
            self.summary = "Completada"


def _now() -> str:
    """Fecha y hora actuales, sin microsegundos."""
    return datetime.now().isoformat("T", "seconds")


def _worst(detail: list[tuple[str, str]]) -> Level | None:
    """Nivel más grave del detalle."""
    levels = [Level(value) for value, _ in detail]
    return max(levels, key=_SEVERITY.__getitem__) if levels else None


def when_label(iso: str, now: datetime | None = None) -> str:
    """Fecha en lenguaje llano: «Hoy, 09:45», «Ayer, 18:02», «3 nov, 10:15».

    Examples:
        >>> when_label("2026-11-08T09:45:00", datetime(2026, 11, 8, 12))
        'Hoy, 09:45'
        >>> when_label("2026-11-07T18:02:00", datetime(2026, 11, 8, 12))
        'Ayer, 18:02'
        >>> when_label("2026-11-03T10:15:00", datetime(2026, 11, 8, 12))
        '3 nov, 10:15'
    """
    moment = datetime.fromisoformat(iso)
    today = (now or datetime.now()).date()
    clock = moment.strftime("%H:%M")
    if moment.date() == today:
        return f"Hoy, {clock}"
    if moment.date() == today - timedelta(days=1):
        return f"Ayer, {clock}"
    months = [
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
    return f"{moment.day} {months[moment.month - 1]}, {clock}"


class ActivityLog:
    """Historial de eventos, el más reciente primero, guardado en JSONL."""

    def __init__(self, path: Path | None) -> None:
        """Carga el historial de ``path`` (sin fichero: solo en memoria)."""
        self.path = path
        self.events: list[Event] = []
        if path is not None:
            self.events = list(reversed(_load(path)))

    def start(self, title: str, category: str = "general") -> Event:
        """Abre un evento en curso."""
        event = Event(title, category)
        self.events.insert(0, event)
        return event

    def save(self, event: Event) -> None:
        """Guarda un evento terminado (y recorta el fichero si crece demasiado)."""
        if self.path is None or event.running:
            return
        record = asdict(event)
        record["level"] = event.level.value
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if len(lines) > MAX_EVENTS:
                self.path.write_text(
                    "\n".join(lines[-MAX_EVENTS:]) + "\n", encoding="utf-8"
                )


def _load(path: Path) -> list[Event]:
    """Eventos del fichero; las líneas que no se entienden se ignoran."""
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-MAX_EVENTS:]:
        try:
            data = json.loads(line)
            events.append(
                Event(
                    title=str(data["title"]),
                    category=str(data["category"]),
                    level=Level(data["level"]),
                    summary=str(data["summary"]),
                    detail=[(str(v), str(m)) for v, m in data["detail"]],
                    when=str(data["when"]),
                    id=str(data["id"]),
                    running=False,
                )
            )
        except (ValueError, KeyError, TypeError):
            continue  # historial informativo: una línea rota no impide abrir
    return events
