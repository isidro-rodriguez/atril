"""Configuración de un temario (``temarios/<id>/temario.toml``).

Un temario agrupa fuentes (``[[fuente]]``) y bases de conocimiento (``[[kb]]``).
Cada fuente pertenece a una sola KB, que la selecciona con patrones de id
(``fnmatch``: ``cte-*``). La norma vinculante y las guías van en KB distintas.
"""

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from acodo.utils import (
    valid_domain,
    valid_filename,
    valid_relative_path,
    valid_slug,
    valid_url,
)

from atril.config._toml import ConfigError, Table, load_toml

SYLLABUS_FILE = "temario.toml"
"""Nombre del fichero de configuración de cada temario."""


class SourceKind(StrEnum):
    """Tipo de fuente y comando de DeepTutor con el que se indexa."""

    PDF = "pdf"
    """Fichero PDF: ``kb add``. Con ``url`` se descarga; sin ella, es manual."""
    MARKDOWN = "markdown"
    """Carpeta de Markdown: ``kb add --docs-dir``."""
    GITHUB = "github"
    """Repositorio: ``kb add-github-source``."""
    WEB = "web"
    """Página web: ``kb add-web-source``."""


class CheckFrequency(StrEnum):
    """Frecuencia con la que ``atril fuentes comprobar`` revisa una fuente."""

    NEVER = "nunca"
    WEEKLY = "semanal"
    MONTHLY = "mensual"


@dataclass(frozen=True, slots=True)
class Source:
    """Fuente ``[[fuente]]``.

    ``folder`` y ``filename`` solo aplican a fuentes locales (``pdf`` y
    ``markdown``) y son relativos a ``fuentes/`` del temario.
    """

    id: str
    kind: SourceKind
    title: str | None
    url: str | None
    folder: str | None
    filename: str | None
    check: CheckFrequency

    @property
    def is_manual(self) -> bool:
        """``True`` si el fichero se coloca a mano (PDF sin URL)."""
        return self.kind is SourceKind.PDF and self.url is None


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    """Base de conocimiento ``[[kb]]`` de DeepTutor."""

    id: str
    binding: bool
    patterns: tuple[str, ...]
    description: str | None
    eval_file: str | None

    def matches(self, source_id: str) -> bool:
        """Indica si algún patrón de la KB selecciona ``source_id``.

        Examples:
            >>> kb = KnowledgeBase("kb", True, ("cte-*", "loe"), None, None)
            >>> kb.matches("cte-db-si"), kb.matches("loe"), kb.matches("rebt")
            (True, True, False)
        """
        return any(fnmatchcase(source_id, pattern) for pattern in self.patterns)


@dataclass(frozen=True, slots=True)
class Syllabus:
    """Temario completo, ya validado."""

    id: str
    root: Path
    name: str
    prompt: str
    web_domains: tuple[str, ...]
    knowledge_bases: tuple[KnowledgeBase, ...]
    sources: tuple[Source, ...]
    warnings: tuple[str, ...]

    @property
    def workspace_dir(self) -> Path:
        """Espacio registrado en DeepTutor (lo único que lee el agente)."""
        return self.root / "espacio"

    @property
    def sources_dir(self) -> Path:
        """Fuentes descargadas o colocadas a mano."""
        return self.root / "fuentes"

    @property
    def history_dir(self) -> Path:
        """Versiones anteriores de las fuentes."""
        return self.sources_dir / "historico"

    def sources_of(self, kb: KnowledgeBase) -> tuple[Source, ...]:
        """Fuentes que pertenecen a ``kb``, en el orden de declaración."""
        return tuple(source for source in self.sources if kb.matches(source.id))


def load_syllabus(root: Path) -> Syllabus:
    """Lee y valida ``<root>/temario.toml``.

    El id del temario es el nombre de la carpeta ``root``.

    Args:
        root: Carpeta del temario.

    Returns:
        El temario validado. Los avisos no bloqueantes (un patrón de KB que no
        selecciona ninguna fuente) quedan en ``warnings``.

    Raises:
        ConfigError: Si el fichero falta o no cumple el esquema.
    """
    path = root / SYLLABUS_FILE
    top = Table(load_toml(path), path)
    if not valid_slug(root.name):
        raise top.error(f"el nombre de la carpeta ({root.name!r}) debe ser un slug.")

    head = top.get_table("temario")
    name = head.get_str("nombre")
    prompt = _relative_path(head, "prompt", "prompt.md") or "prompt.md"
    domains = head.get_str_list("dominios_web", [])
    for domain in domains:
        if not valid_domain(domain):
            raise head.error(f"dominio no válido: {domain!r}.")
    head.close()

    sources = tuple(_source(table) for table in top.get_table_list("fuente"))
    kbs = tuple(_kb(table) for table in top.get_table_list("kb"))
    top.close()

    _check_unique(top, "fuente", [source.id for source in sources])
    _check_unique(top, "kb", [kb.id for kb in kbs])
    warnings = _check_membership(top, kbs, sources)

    return Syllabus(
        id=root.name,
        root=root.resolve(),
        name=name,
        prompt=prompt,
        web_domains=tuple(domains),
        knowledge_bases=kbs,
        sources=sources,
        warnings=warnings,
    )


def _relative_path(table: Table, key: str, default: str | None = None) -> str | None:
    """Ruta relativa con ``/``, sin salir de la carpeta; ``default`` si falta."""
    value = table.get_str(key, default)
    if value is None:
        return None
    if not valid_relative_path(value):
        raise table.error(f"'{key}' debe ser una ruta relativa válida: {value!r}.")
    # Se normaliza a "/" y sin segmentos vacíos ni ".", igual en Windows y Linux.
    return "/".join(PurePosixPath(value.replace("\\", "/")).parts)


def _id(table: Table) -> str:
    """Clave ``id`` en formato slug."""
    value = table.get_str("id")
    if not valid_slug(value):
        raise table.error(
            f"'id' debe ser un slug (minúsculas, cifras y '-'): {value!r}."
        )
    return value


def _source(table: Table) -> Source:
    """Tabla ``[[fuente]]``."""
    source_id = _id(table)
    kind_text = table.get_str("tipo")
    try:
        kind = SourceKind(kind_text)
    except ValueError:
        options = ", ".join(kind.value for kind in SourceKind)
        raise table.error(f"'tipo' debe ser uno de: {options}.") from None

    url = table.get_str("url", None)
    if url is not None and not valid_url(url):
        raise table.error(f"'url' no es una URL válida: {url!r}.")

    check_text = table.get_str("comprobar", CheckFrequency.NEVER.value)
    try:
        check = CheckFrequency(check_text)
    except ValueError:
        options = ", ".join(freq.value for freq in CheckFrequency)
        raise table.error(f"'comprobar' debe ser uno de: {options}.") from None

    local = kind in {SourceKind.PDF, SourceKind.MARKDOWN}
    folder = _relative_path(table, "carpeta") if local else None
    if local and folder is None:
        raise table.error(f"una fuente {kind} necesita 'carpeta'.")
    filename = table.get_str("archivo", None)

    if kind is SourceKind.PDF:
        if filename is None and url is not None:
            filename = PurePosixPath(urlsplit(url).path).name
        if filename is None:
            raise table.error("un PDF sin 'url' (manual) necesita 'archivo'.")
        if not valid_filename(filename) or not filename.lower().endswith(".pdf"):
            raise table.error(f"'archivo' debe ser un nombre de PDF: {filename!r}.")
    elif filename is not None:
        raise table.error(f"'archivo' solo aplica a fuentes pdf, no a {kind}.")

    if kind in {SourceKind.GITHUB, SourceKind.WEB} and url is None:
        raise table.error(f"una fuente {kind} necesita 'url'.")
    if kind is SourceKind.MARKDOWN and url is not None:
        raise table.error("una fuente markdown es local: no lleva 'url'.")
    if url is None and check is not CheckFrequency.NEVER:
        raise table.error("solo se pueden comprobar fuentes con 'url'.")

    source = Source(
        id=source_id,
        kind=kind,
        title=table.get_str("titulo", None),
        url=url,
        folder=folder,
        filename=filename,
        check=check,
    )
    table.close()
    return source


def _kb(table: Table) -> KnowledgeBase:
    """Tabla ``[[kb]]``."""
    kb = KnowledgeBase(
        id=_id(table),
        binding=table.get_bool("vinculante"),
        patterns=tuple(table.get_str_list("fuentes")),
        description=table.get_str("descripcion", None),
        eval_file=_relative_path(table, "evaluacion"),
    )
    if not kb.patterns:
        raise table.error("'fuentes' debe tener al menos un patrón.")
    table.close()
    return kb


def _check_unique(top: Table, kind: str, ids: list[str]) -> None:
    """Falla si hay ids repetidos."""
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise top.error(f"id de {kind} repetido: {item!r}.")
        seen.add(item)


def _check_membership(
    top: Table, kbs: tuple[KnowledgeBase, ...], sources: tuple[Source, ...]
) -> tuple[str, ...]:
    """Cada fuente, en una sola KB. Devuelve avisos de patrones sin coincidencias."""
    for source in sources:
        owners = [kb.id for kb in kbs if kb.matches(source.id)]
        if not owners:
            raise top.error(f"la fuente {source.id!r} no pertenece a ninguna KB.")
        if len(owners) > 1:
            raise top.error(
                f"la fuente {source.id!r} está en varias KB: {', '.join(owners)}."
            )

    return tuple(
        f"KB {kb.id!r}: el patrón {pattern!r} no selecciona fuentes."
        for kb in kbs
        for pattern in kb.patterns
        if not any(fnmatchcase(source.id, pattern) for source in sources)
    )


def load_syllabi(syllabi_dir: Path) -> tuple[list[Syllabus], list[str]]:
    """Carga todos los temarios de ``syllabi_dir`` (subcarpetas con ``temario.toml``).

    Comprueba además que los id de KB no se repitan entre temarios, porque en
    DeepTutor son globales.

    Args:
        syllabi_dir: Carpeta ``temarios/`` de la estación.

    Returns:
        Los temarios, ordenados por id, y los avisos de todos ellos.

    Raises:
        ConfigError: Si un temario no es válido o un id de KB se repite.
    """
    syllabi: list[Syllabus] = []
    warnings: list[str] = []
    if not syllabi_dir.is_dir():
        return syllabi, [f"No existe la carpeta de temarios {syllabi_dir}."]

    for folder in sorted(path for path in syllabi_dir.iterdir() if path.is_dir()):
        if not (folder / SYLLABUS_FILE).is_file():
            warnings.append(f"{folder.name}: carpeta sin {SYLLABUS_FILE}, se ignora.")
            continue
        syllabus = load_syllabus(folder)
        syllabi.append(syllabus)
        warnings.extend(f"{syllabus.id}: {warning}" for warning in syllabus.warnings)

    owner: dict[str, str] = {}
    for syllabus in syllabi:
        for kb in syllabus.knowledge_bases:
            if kb.id in owner:
                raise ConfigError(
                    f"La KB {kb.id!r} está en los temarios {owner[kb.id]!r} y "
                    f"{syllabus.id!r}; los id de KB deben ser únicos en la estación."
                )
            owner[kb.id] = syllabus.id
    return syllabi, warnings


__all__ = [
    "CheckFrequency",
    "ConfigError",
    "KnowledgeBase",
    "Source",
    "SourceKind",
    "Syllabus",
    "load_syllabi",
    "load_syllabus",
]
