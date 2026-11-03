"""Descarga, comprobación e histórico de las fuentes de un temario.

Cada fuente ``pdf`` con ``url`` se guarda con un nombre estable en
``fuentes/<carpeta>/<archivo>``. El registro ``fuentes/registro.json`` anota su
hash y fechas; al comprobarla, si el hash cambia, la versión anterior pasa a
``fuentes/historico/<carpeta>/<nombre>.<AAAA-MM-DD>.pdf``.
"""

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from acodo.utils import get_file_hash, get_now

from atril import net
from atril.config._toml import StateFileError, load_state
from atril.config.syllabus import CheckFrequency, Source, SourceKind, Syllabus

PDF_MAGIC = b"%PDF-"
"""Cabecera de todo PDF; una descarga que no la tiene es una página de error."""

CHUNK = 1024 * 256
"""Tamaño de bloque de las descargas."""

CHECK_INTERVAL = {
    CheckFrequency.WEEKLY: timedelta(days=7),
    CheckFrequency.MONTHLY: timedelta(days=30),
}
"""Antigüedad a partir de la cual toca volver a comprobar una fuente."""

Progress = Callable[[int, int | None], None]
"""Avance de una descarga: bytes recibidos y total (``None`` si no se conoce)."""


class DownloadError(Exception):
    """La descarga ha fallado; el mensaje está en español."""


@dataclass(slots=True)
class SourceRecord:
    """Entrada del registro de una fuente."""

    url: str
    sha256: str
    size: int
    downloaded_at: str
    checked_at: str


class Registry:
    """Registro ``fuentes/registro.json`` de un temario."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        """Carga el registro de ``path`` (vacío si no existe).

        Raises:
            StateFileError: Si el fichero está dañado.
        """
        self.path = path
        try:
            self.records: dict[str, SourceRecord] = {
                key: SourceRecord(**value)
                for key, value in load_state(path, "fuentes").items()
            }
        except TypeError as exc:
            raise StateFileError(
                f"{path}: entrada con campos inesperados ({exc}); corrígelo o "
                "recupéralo de git o del backup; atril no lo sobrescribe."
            ) from exc

    def get(self, source_id: str) -> SourceRecord | None:
        """Entrada de una fuente, si la hay."""
        return self.records.get(source_id)

    def save(self) -> None:
        """Escribe el registro (ordenado, para que los diffs de git sean legibles)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.VERSION,
            "fuentes": {key: asdict(self.records[key]) for key in sorted(self.records)},
        }
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        self.path.write_text(text, encoding="utf-8")


class Outcome(StrEnum):
    """Resultado de descargar o comprobar una fuente."""

    DOWNLOADED = "descargada"
    PRESENT = "ya presente"
    UNCHANGED = "sin cambios"
    UPDATED = "actualizada"
    NOT_DUE = "no toca"
    MANUAL = "manual"
    MISSING = "falta"
    REMOTE = "remota"
    FAILED = "error"


@dataclass(frozen=True, slots=True)
class Result:
    """Resultado de una fuente, con detalle legible."""

    source: Source
    outcome: Outcome
    detail: str = ""


def now_iso() -> str:
    """Fecha y hora actual en UTC, ISO 8601 sin microsegundos."""
    return get_now().replace(microsecond=0).isoformat()


def is_due(source: Source, record: SourceRecord | None, now: datetime) -> bool:
    """Indica si toca comprobar la fuente según su frecuencia y la última comprobación.

    Examples:
        >>> from datetime import UTC
        >>> src = Source("a", SourceKind.PDF, None, "https://x.es/a.pdf", "d",
        ...              "a.pdf", CheckFrequency.WEEKLY)
        >>> rec = SourceRecord("u", "h", 1, "2026-01-01T00:00:00+00:00",
        ...                    "2026-01-01T00:00:00+00:00")
        >>> is_due(src, rec, datetime(2026, 1, 5, tzinfo=UTC))
        False
        >>> is_due(src, rec, datetime(2026, 1, 9, tzinfo=UTC))
        True
    """
    interval = CHECK_INTERVAL.get(source.check)
    if interval is None or source.url is None:
        return False
    if record is None:
        return True
    return now - datetime.fromisoformat(record.checked_at) >= interval


def download(
    url: str, target: Path, progress: Progress | None = None
) -> tuple[str, int]:
    """Descarga ``url`` en ``target`` validando que sea un PDF.

    Escribe primero en ``<target>.part`` y solo lo renombra si la descarga es
    completa y empieza por ``%PDF-``; así nunca queda un PDF a medias.

    Args:
        url: Dirección del PDF.
        target: Fichero de destino.
        progress: Función de avance opcional.

    Returns:
        Hash SHA-256 y tamaño en bytes.

    Raises:
        DownloadError: Si falla la red o el contenido no es un PDF.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with net.open_url(url) as response, part.open("wb") as out:
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            while block := response.read(CHUNK):
                if size == 0 and not block.startswith(PDF_MAGIC):
                    raise DownloadError(
                        "la respuesta no es un PDF (¿página de error?)."
                    )
                out.write(block)
                digest.update(block)
                size += len(block)
                if progress:
                    progress(size, total)
        if size == 0:
            raise DownloadError("la respuesta está vacía.")
    except OSError as exc:
        part.unlink(missing_ok=True)
        reason = getattr(exc, "reason", None) or exc  # URLError envuelve el motivo
        raise DownloadError(f"no se puede descargar: {reason}.") from exc
    except DownloadError:
        part.unlink(missing_ok=True)
        raise
    part.replace(target)
    return digest.hexdigest(), size


def archive(current: Path, syllabus: Syllabus, record: SourceRecord | None) -> Path:
    """Mueve la versión actual de una fuente a ``fuentes/historico/``.

    El nombre lleva la fecha de descarga de esa versión (o la de hoy si no consta).

    Returns:
        La ruta en el histórico.
    """
    relative = current.relative_to(syllabus.sources_dir)
    stamp = (record.downloaded_at if record else now_iso())[:10]
    target = (
        syllabus.history_dir
        / relative.parent
        / f"{current.stem}.{stamp}{current.suffix}"
    )
    counter = 2
    while target.exists():
        name = f"{current.stem}.{stamp}-{counter}{current.suffix}"
        target = target.with_name(name)
        counter += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(current, target)
    return target


class SourceManager:
    """Operaciones sobre las fuentes de un temario."""

    def __init__(self, syllabus: Syllabus) -> None:
        """Prepara las operaciones y carga el registro."""
        self.syllabus = syllabus
        self.registry = Registry(syllabus.registry_file)

    def fetch(self, source: Source, progress: Progress | None = None) -> Result:
        """Descarga una fuente si falta; no toca las que ya están."""
        path = self.syllabus.source_path(source)
        if path is None:
            return Result(source, Outcome.REMOTE, "la indexa DeepTutor desde su URL")
        if source.kind is SourceKind.MARKDOWN:
            return self._local(source, path)
        if path.is_file():
            if self.registry.get(source.id) is None and source.url:
                self._record(source, path, source.url)
            return Result(source, Outcome.PRESENT)
        if source.url is None:
            return Result(source, Outcome.MANUAL, f"colócala en {path}")
        try:
            sha, size = download(source.url, path, progress)
        except DownloadError as exc:
            return Result(source, Outcome.FAILED, str(exc))
        stamp = now_iso()
        self.registry.records[source.id] = SourceRecord(
            source.url, sha, size, stamp, stamp
        )
        return Result(source, Outcome.DOWNLOADED)

    def check(self, source: Source, progress: Progress | None = None) -> Result:
        """Vuelve a descargar una fuente y la sustituye si ha cambiado.

        Raises:
            ValueError: Si la fuente no tiene ``url``.
        """
        if source.url is None:
            raise ValueError(f"la fuente {source.id} no tiene url.")
        path = self.syllabus.source_path(source)
        if path is None:
            return Result(source, Outcome.REMOTE, "la indexa DeepTutor desde su URL")
        if not path.is_file():
            return self.fetch(source, progress)

        record = self.registry.get(source.id)
        temp = path.with_name(path.name + ".nuevo")
        try:
            sha, size = download(source.url, temp, progress)
        except DownloadError as exc:
            return Result(source, Outcome.FAILED, str(exc))
        stamp = now_iso()
        current_sha = record.sha256 if record else get_file_hash(path)
        if sha == current_sha:
            temp.unlink()
            downloaded = record.downloaded_at if record else stamp
            self.registry.records[source.id] = SourceRecord(
                source.url, sha, size, downloaded, stamp
            )
            return Result(source, Outcome.UNCHANGED)

        old = archive(path, self.syllabus, record)
        temp.replace(path)
        self.registry.records[source.id] = SourceRecord(
            source.url, sha, size, stamp, stamp
        )
        relative = old.relative_to(self.syllabus.root)
        return Result(source, Outcome.UPDATED, f"versión anterior en {relative}")

    def local_state(self, source: Source) -> str:
        """Estado del fichero local frente al registro, para informes."""
        path = self.syllabus.source_path(source)
        if path is None:
            return "remota"
        if not path.exists():
            return "falta"
        if source.kind is SourceKind.MARKDOWN:
            return "presente"
        record = self.registry.get(source.id)
        if record is None:
            return "sin registro" if source.url else "manual"
        return "presente" if get_file_hash(path) == record.sha256 else "modificada"

    def _local(self, source: Source, folder: Path) -> Result:
        """Carpeta de Markdown: solo se comprueba que exista y tenga ``.md``."""
        if folder.is_dir() and any(folder.rglob("*.md")):
            return Result(source, Outcome.PRESENT)
        return Result(source, Outcome.MISSING, f"pon los .md en {folder}")

    def _record(self, source: Source, path: Path, url: str) -> None:
        """Registra un fichero que ya estaba (descargado antes de usar atril)."""
        stamp = now_iso()
        self.registry.records[source.id] = SourceRecord(
            url, get_file_hash(path), path.stat().st_size, stamp, stamp
        )
