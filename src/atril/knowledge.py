"""Indexado de las KB de DeepTutor a partir de las fuentes de un temario.

- Los documentos se añaden **uno a uno** con el CLI de DeepTutor
  (``kb create|add --doc``): si algo falla, se reanuda desde el siguiente y
  DeepTutor reutiliza el parseo en caché.
- ``fuentes/indexado.json`` registra qué versión (hash) de cada fuente está en
  cada KB.
- Una fuente cambiada no se puede volver a añadir sin más: DeepTutor guardaría
  la nueva como ``nombre (2).pdf`` junto a la anterior. Se quita antes la
  versión anterior (API), se añade la nueva y se reindexa la KB, porque
  DeepTutor no purga los vectores de lo que se quita.
- El reindexado y el borrado de documentos van por la API HTTP de DeepTutor.
"""

import hashlib
import json
import subprocess
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import psutil
from acodo.utils import get_file_hash

from atril import net
from atril.config._toml import StateFileError, load_state
from atril.config.station import Station
from atril.config.syllabus import KnowledgeBase, Source, SourceKind, Syllabus
from atril.processes import kill_tree, lower_priority

STALL_SECONDS = 15 * 60
"""Sin actividad durante este tiempo, el indexado probablemente está colgado."""

POLL_SECONDS = 3.0
"""Intervalo de consulta del progreso."""

RETRY_STATES = frozenset({"failed", "interrupted", "partial", "cancelled"})
"""Estados de un run que dejan el worker de DeepTutor atascado hasta reiniciarlo."""

_ALREADY_INDEXED = ("already indexed", "No new unique documents")
"""Mensajes de DeepTutor cuando el contenido ya está en la KB (cuenta como éxito)."""

_SELECTION_SCRIPT = (
    "import json; from deeptutor.services.rag.embedding_binding import "
    "default_selection as d; print(json.dumps(d() or {}))"
)
"""Modelo de embedding activo; enviarlo en el reindexado lo fuerza."""


# --- estado de DeepTutor -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KbRun:
    """Último indexado de una KB según ``.indexing-run.json`` de DeepTutor."""

    raw: dict[str, Any]

    @classmethod
    def load(cls, kb_dir: Path) -> "KbRun | None":
        """Lee el run de ``kb_dir``; ``None`` si no hay o no se puede leer."""
        try:
            data = json.loads(
                (kb_dir / ".indexing-run.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None
        return cls(data) if isinstance(data, dict) else None

    @property
    def task_id(self) -> str | None:
        """Identificador del run."""
        return self.raw.get("task_id")

    @property
    def state(self) -> str:
        """Estado; un ``running`` cuyo proceso ha muerto cuenta como ``interrupted``."""
        state = str(self.raw.get("state") or "")
        if state == "running" and not self._owner_alive():
            return "interrupted"
        return state

    @property
    def error(self) -> str:
        """Mensaje de error del run, si lo hay."""
        return str(self.raw.get("error") or "")

    def describe(self, now: float) -> str:
        """Fase, avance y actividad en una línea."""
        phase = self.raw.get("phase") or "?"
        total, current = self.raw.get("phase_total"), self.raw.get("phase_current")
        parts = [str(phase)]
        documents = self.raw.get("documents")
        if isinstance(documents, dict) and len(documents) > 1:
            done = sum(
                1
                for d in documents.values()
                if isinstance(d, dict) and d.get("status") == "completed"
            )
            parts.append(f"docs {done}/{len(documents)}")
        if total:
            parts.append(f"{current or 0}/{total}")
        idle = self.idle_seconds(now)
        if idle is not None:
            parts.append(f"actividad hace {int(idle)} s")
        return " · ".join(parts)

    def idle_seconds(self, now: float) -> float | None:
        """Segundos desde la última actividad registrada."""
        last = self.raw.get("last_activity_at")
        return max(0.0, now - float(last)) if last else None

    def _owner_alive(self) -> bool:
        """El proceso que escribe el run sigue vivo (mismo PID y hora de inicio)."""
        try:
            process = psutil.Process(int(self.raw["pid"]))
            started = self.raw.get("process_started_at")
            return started is None or abs(process.create_time() - float(started)) < 1
        except (psutil.Error, KeyError, TypeError, ValueError):
            return False


# --- registro propio -----------------------------------------------------------


@dataclass(slots=True)
class IndexedSource:
    """Versión de una fuente indexada en una KB."""

    file: str
    sha256: str
    indexed_at: str
    minutes: float | None = None


@dataclass(slots=True)
class KbLedger:
    """Registro de una KB."""

    pending_reindex: bool = False
    sources: dict[str, IndexedSource] = field(default_factory=dict)


class Ledger:
    """Registro ``fuentes/indexado.json`` de un temario (texto, versionable)."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        """Carga el registro (vacío si no existe).

        Raises:
            StateFileError: Si el fichero está dañado.
        """
        self.path = path
        self.kbs: dict[str, KbLedger] = {}
        try:
            for kb_id, entry in load_state(path, "kb").items():
                sources = {
                    key: IndexedSource(**value)
                    for key, value in entry.get("fuentes", {}).items()
                }
                self.kbs[kb_id] = KbLedger(bool(entry.get("reindexar")), sources)
        except (AttributeError, TypeError) as exc:
            raise StateFileError(
                f"{path}: entrada con formato inesperado ({exc}); corrígelo o "
                "recupéralo de git o del backup; atril no lo sobrescribe."
            ) from exc

    def kb(self, kb_id: str) -> KbLedger:
        """Registro de una KB (se crea vacío si no existe)."""
        return self.kbs.setdefault(kb_id, KbLedger())

    def save(self) -> None:
        """Escribe el registro, ordenado para diffs legibles."""
        data = {
            "version": self.VERSION,
            "kb": {
                kb_id: {
                    "reindexar": entry.pending_reindex,
                    "fuentes": {
                        key: asdict(entry.sources[key]) for key in sorted(entry.sources)
                    },
                }
                for kb_id, entry in sorted(self.kbs.items())
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self.path.write_text(text, encoding="utf-8")


def ledger_path(syllabus: Syllabus) -> Path:
    """Ruta del registro de indexado de un temario."""
    return syllabus.sources_dir / "indexado.json"


# --- plan ----------------------------------------------------------------------


class PlanState(StrEnum):
    """Situación de una fuente frente a lo indexado."""

    INDEXED = "indexada"
    NEW = "nueva"
    CHANGED = "cambiada"
    MISSING = "sin fichero"
    REMOVED = "retirada"


@dataclass(frozen=True, slots=True)
class PlanItem:
    """Fuente de una KB y lo que hay que hacer con ella."""

    source_id: str
    state: PlanState
    source: Source | None = None
    path: Path | None = None
    digest: str = ""
    file: str = ""


def content_digest(source: Source, path: Path | None) -> str:
    """Huella del contenido: hash del PDF, de la carpeta Markdown o la URL remota."""
    if path is None:
        return f"url:{source.url}"
    if path.is_file():
        return get_file_hash(path)
    digest = hashlib.sha256()
    for file in sorted(path.rglob("*.md")):
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(get_file_hash(file).encode())
    return digest.hexdigest()


def plan(syllabus: Syllabus, kb: KnowledgeBase, ledger: Ledger) -> list[PlanItem]:
    """Compara las fuentes de ``kb`` con su registro."""
    recorded = ledger.kb(kb.id).sources
    items = []
    for source in syllabus.sources_of(kb):
        path = syllabus.source_path(source)
        if path is not None and not path.exists():
            items.append(PlanItem(source.id, PlanState.MISSING, source, path))
            continue
        digest = content_digest(source, path)
        file = path.name if path else source.id
        previous = recorded.get(source.id)
        if previous is None:
            state = PlanState.NEW
        elif previous.sha256 == digest:
            state = PlanState.INDEXED
        else:
            state = PlanState.CHANGED
        items.append(PlanItem(source.id, state, source, path, digest, file))
    current = {source.id for source in syllabus.sources_of(kb)}
    items.extend(
        PlanItem(key, PlanState.REMOVED, file=entry.file)
        for key, entry in sorted(recorded.items())
        if key not in current
    )
    return items


# --- indexado con el CLI -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AddResult:
    """Resultado de añadir una fuente a una KB."""

    ok: bool
    minutes: float
    detail: str = ""
    log: Path | None = None


THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
"""Variables con las que PyTorch, NumPy y Docling limitan sus hilos de CPU."""

Tick = Callable[[KbRun | None, float], None]
"""Avance: run actual (si lo hay) y segundos transcurridos."""


class Indexer:
    """Añade fuentes a las KB de una estación con el CLI de DeepTutor."""

    def __init__(self, station: Station, env: dict[str, str]) -> None:
        """Prepara el indexador con el entorno de ``deeptutor``."""
        self.station = station
        self.env = env

    def _env(self) -> dict[str, str]:
        """Entorno del CLI, con el límite de hilos de ``[indexado] hilos``."""
        threads = self.station.indexing.threads
        if not threads:
            return self.env
        return {**self.env, **dict.fromkeys(THREAD_VARIABLES, str(threads))}

    def kb_exists(self, kb_id: str) -> bool:
        """La KB ya existe en DeepTutor."""
        return (self.station.kb_dir(kb_id) / "metadata.json").is_file()

    def command(self, kb_id: str, item: PlanItem) -> list[str]:
        """Comando de DeepTutor para añadir la fuente (crea la KB si hace falta)."""
        source = item.source
        if source is None:
            raise ValueError("solo se pueden añadir fuentes del temario.")
        cli = str(self.station.deeptutor_cli)
        if source.kind is SourceKind.GITHUB:
            return [cli, "kb", "add-github-source", kb_id, "--repo", str(source.url)]
        if source.kind is SourceKind.WEB:
            return [cli, "kb", "add-web-source", kb_id, "--url", str(source.url)]
        action = "add" if self.kb_exists(kb_id) else "create"
        option = "--docs-dir" if source.kind is SourceKind.MARKDOWN else "--doc"
        return [cli, "kb", action, kb_id, option, str(item.path)]

    def add(self, kb_id: str, item: PlanItem, tick: Tick | None = None) -> AddResult:
        """Añade una fuente y espera a que termine, informando del avance.

        Si se interrumpe (Ctrl+C), cierra el proceso de DeepTutor y relanza la
        interrupción: al repetir el comando se continúa por esta fuente.
        """
        source = item.source
        if source is None:
            raise ValueError("solo se pueden añadir fuentes del temario.")
        command = self.command(kb_id, item)
        remote = source.kind in {SourceKind.GITHUB, SourceKind.WEB}
        if remote and not self.kb_exists(kb_id):
            return AddResult(
                False,
                0.0,
                "una KB no se crea con una fuente remota; añade antes un documento.",
            )

        kb_dir = self.station.kb_dir(kb_id)
        previous = KbRun.load(kb_dir)
        previous_task = previous.task_id if previous else None
        self.station.logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_log = self.station.logs_dir / f"indexado-{kb_id}-{stamp}.log"
        started = time.monotonic()
        with out_log.open("w", encoding="utf-8") as out:
            process = subprocess.Popen(
                command, stdout=out, stderr=subprocess.STDOUT, env=self._env()
            )
            lower_priority(process.pid)
            try:
                while process.poll() is None:
                    time.sleep(POLL_SECONDS)
                    if tick:
                        tick(KbRun.load(kb_dir), time.monotonic() - started)
            except BaseException:
                kill_tree(process.pid)
                raise
        minutes = (time.monotonic() - started) / 60
        output = out_log.read_text(encoding="utf-8", errors="replace")
        run = KbRun.load(kb_dir)

        # El documento puede quedar con otro nombre en raw/; basta con que haya un
        # run nuevo y completado.
        completed = (
            run is not None
            and run.task_id != previous_task
            and run.state == "completed"
        )
        duplicate = any(text in output for text in _ALREADY_INDEXED)
        if process.returncode == 0 and (completed or duplicate or remote):
            return AddResult(
                True, minutes, "ya estaba (mismo contenido)" if duplicate else ""
            )
        detail = (run.error if run else "") or f"código de salida {process.returncode}"
        return AddResult(False, minutes, detail, out_log)


# --- API de DeepTutor ----------------------------------------------------------


class KnowledgeApi:
    """Operaciones de KB que solo ofrece la API HTTP de DeepTutor."""

    def __init__(self, station: Station) -> None:
        """Usa el backend de la estación."""
        port = station.deeptutor.backend_port
        self.base = f"http://127.0.0.1:{port}/api/knowledge-bases"

    def delete_file(self, kb_id: str, filename: str) -> bool:
        """Quita un documento de ``raw/``; devuelve si estaba indexado.

        DeepTutor no purga sus vectores: hay que reindexar después.
        """
        quoted = urllib.parse.quote(filename)
        reply = net.request_json(f"{self.base}/{kb_id}/files/{quoted}", method="DELETE")
        return bool(reply and reply.get("was_indexed"))

    def reindex(self, kb_id: str, embedding_model: str) -> dict[str, Any]:
        """Lanza el reindexado completo (rehace chunks y embeddings).

        Raises:
            net.HttpError: Si DeepTutor lo rechaza (p. ej. un worker en marcha).
        """
        url = f"{self.base}/{urllib.parse.quote(kb_id)}/reindex"
        form = {"embedding_model": embedding_model}
        try:
            return net.request_json(url, method="POST", form=form, timeout=120) or {}
        except net.HttpError as exc:
            if exc.status != 404:
                raise
            # KB de la biblioteca de recursos (otro ámbito en DeepTutor).
            return (
                net.request_json(
                    f"{url}?resource_library=true",
                    method="POST",
                    form=form,
                    timeout=120,
                )
                or {}
            )


def embedding_selection(station: Station, env: dict[str, str]) -> str:
    """Modelo de embedding activo en DeepTutor, como JSON (``{}`` si no hay).

    Raises:
        OSError: Si no se puede ejecutar el Python de ``app/``.
    """
    result = subprocess.run(
        [str(station.venv_python), "-c", _SELECTION_SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    lines = result.stdout.strip().splitlines()
    return lines[-1] if result.returncode == 0 and lines else "{}"
