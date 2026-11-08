"""Ajustes de ``atril.toml`` desde la ventana, sin editar TOML a mano.

El fichero se edita con ``tomlkit`` (conserva comentarios y orden), se valida
entero como si ya estuviera escrito y se sustituye vía ``.nuevo``: un valor
erróneo no llega a guardarse. ``atril.toml`` sigue siendo la única fuente de
configuración. :func:`effects` dice qué hay que hacer después de un cambio
(aplicarlo a DeepTutor, reinstalar, reindexar...).
"""

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

import tomlkit
from tomlkit.container import Container
from tomlkit.items import InlineTable, Table

from atril.config.station import STATION_FILE, Station, check_station_text
from atril.errors import AtrilError

Value = str | int | bool | list[str]
"""Valor de una clave de ``atril.toml`` que se puede cambiar desde aquí."""

EDITABLE = {
    "deeptutor": ("repo", "rama", "python", "parches", "paquetes", "busqueda"),
    "deeptutor.puertos": ("backend", "frontend"),
    "deeptutor.llm": ("proveedor", "modelo"),
    "ollama": ("url", "embedding", "dimension", "contexto"),
    "indexado": (
        "parser",
        "chunk",
        "solape",
        "descargar_modelos",
        "hilos",
        "lote_embedding",
        "pausa_embedding",
    ),
    "backup": ("destinos", "formato", "conservar"),
}
"""Claves que se pueden cambiar desde la ventana, por tabla (todas las del esquema)."""

OPTIONAL_TABLES = frozenset({"ollama", "deeptutor.llm"})
"""Tablas que se pueden quitar enteras."""

Changes = Mapping[str, Mapping[str, Value | None] | None]
"""Cambios por tabla: valor nuevo, ``None`` para volver al valor por defecto, o la
tabla entera a ``None`` para quitarla (solo :data:`OPTIONAL_TABLES`)."""


class Effect(StrEnum):
    """Lo que hace falta después de guardar un cambio."""

    APPLY = "aplicar la configuración a DeepTutor"
    PATCHES = "aplicar los parches"
    REINSTALL = "reinstalar DeepTutor (Instalar o reparar)"
    REINDEX = "reindexar los temarios"


def update(station: Station, changes: Changes) -> Station:
    """Cambia claves de ``atril.toml`` y devuelve la estación ya validada.

    Args:
        station: Estación actual.
        changes: Por ejemplo ``{"backup": {"conservar": 10}, "ollama": None}``.

    Returns:
        La estación con los cambios.

    Raises:
        AtrilError: Si una clave no se puede cambiar aquí, el resultado no es
            válido (mensaje de :class:`~atril.config.ConfigError`) o no se puede
            escribir.
    """
    path = station.root / STATION_FILE
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    for table_name, values in changes.items():
        if table_name not in EDITABLE:
            raise AtrilError(f"[{table_name}] no se cambia desde aquí.")
        if values is None:
            if table_name not in OPTIONAL_TABLES:
                raise AtrilError(f"[{table_name}] no se puede quitar.")
            _remove(doc, table_name)
            continue
        table = _table(doc, table_name, path)
        for key, value in values.items():
            if key not in EDITABLE[table_name]:
                raise AtrilError(f"[{table_name}] {key} no se cambia desde aquí.")
            if value is None:
                table.pop(key, None)
            else:
                table[key] = value
    text = tomlkit.dumps(doc)
    updated = check_station_text(text, station.root)
    _replace(path, text)
    return updated


def effects(before: Station, after: Station) -> list[Effect]:
    """Qué hay que hacer para que los cambios de ``atril.toml`` surtan efecto.

    Las copias de seguridad y el ritmo del indexado no necesitan nada: se leen
    en cada operación.
    """
    old, new = before.deeptutor, after.deeptutor
    found = []
    if (old.repo, old.branch, old.python, old.packages) != (
        new.repo,
        new.branch,
        new.python,
        new.packages,
    ):
        found.append(Effect.REINSTALL)
    if old.patches != new.patches:
        found.append(Effect.PATCHES)
    if (
        (old.llm, old.search, old.backend_port, old.frontend_port)
        != (new.llm, new.search, new.backend_port, new.frontend_port)
        or before.ollama != after.ollama
        or before.indexing.parser != after.indexing.parser
    ):
        found.append(Effect.APPLY)
    old_vectors = _vectors(before)
    new_vectors = _vectors(after)
    old_chunks = (
        before.indexing.parser,
        before.indexing.chunk_size,
        before.indexing.chunk_overlap,
    )
    new_chunks = (
        after.indexing.parser,
        after.indexing.chunk_size,
        after.indexing.chunk_overlap,
    )
    if (old_vectors and new_vectors and old_vectors != new_vectors) or (
        old_chunks != new_chunks
    ):
        found.append(Effect.REINDEX)
    return found


def _vectors(station: Station) -> tuple[str, int] | None:
    """Modelo y dimensión de embedding: si cambian, los vectores no sirven."""
    if station.ollama is None:
        return None
    return station.ollama.embedding, station.ollama.dimension


def _table(doc: Container, name: str, path: Path) -> Table | InlineTable:
    """Tabla ``name`` (con puntos), creándola si no existe."""
    current: Container | Table | InlineTable = doc
    for part in name.split("."):
        child = current.get(part)
        if child is None:
            child = tomlkit.table()
            current[part] = child
        if not isinstance(child, Table | InlineTable):
            raise AtrilError(f"{path}: [{name}] no es una tabla.")
        current = child
    assert isinstance(current, Table | InlineTable)
    return current


def _remove(doc: Container, name: str) -> None:
    """Quita la tabla ``name`` (con puntos) si existe."""
    *parents, last = name.split(".")
    current: Container | Table | InlineTable = doc
    for part in parents:
        child = current.get(part)
        if not isinstance(child, Table | InlineTable):
            return
        current = child
    current.pop(last, None)


def _replace(path: Path, text: str) -> None:
    """Sustituye ``path`` por ``text`` de forma atómica."""
    partial = path.with_name(path.name + ".nuevo")
    try:
        partial.write_text(text, encoding="utf-8")
        partial.replace(path)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise AtrilError(f"no se puede escribir {path}: {exc}") from exc
