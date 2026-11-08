"""Ajustes guiados de ``atril.toml``: copias de seguridad y ritmo del indexado.

Solo unas pocas claves, las que tiene sentido tocar sin saber TOML. El fichero
se edita con ``tomlkit`` (conserva comentarios y orden), se valida entero como si
ya estuviera escrito y se sustituye vía ``.nuevo``: un valor erróneo no llega a
guardarse. ``atril.toml`` sigue siendo la única fuente de configuración.
"""

from collections.abc import Mapping
from pathlib import Path

import tomlkit
from tomlkit.items import Table

from atril.config.station import STATION_FILE, Station, check_station_text
from atril.errors import AtrilError

Value = str | int | bool | list[str]
"""Valor de una clave de ``atril.toml`` que se puede cambiar desde aquí."""

EDITABLE = {
    "backup": ("destinos", "formato", "conservar"),
    "indexado": ("hilos", "lote_embedding", "pausa_embedding"),
}
"""Claves que se pueden cambiar desde la ventana, por tabla."""


def update(station: Station, changes: Mapping[str, Mapping[str, Value]]) -> Station:
    """Cambia claves de ``atril.toml`` y devuelve la estación ya validada.

    Args:
        station: Estación actual.
        changes: ``{"backup": {"conservar": 10}, ...}``; solo claves de
            :data:`EDITABLE`.

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
        allowed = EDITABLE.get(table_name, ())
        table = doc.get(table_name)
        if table is None:
            table = tomlkit.table()
            doc[table_name] = table
        if not isinstance(table, Table):
            raise AtrilError(f"{path}: [{table_name}] no es una tabla.")
        for key, value in values.items():
            if key not in allowed:
                raise AtrilError(f"[{table_name}] {key} no se cambia desde aquí.")
            table[key] = value
    text = tomlkit.dumps(doc)
    updated = check_station_text(text, station.root)
    _replace(path, text)
    return updated


def _replace(path: Path, text: str) -> None:
    """Sustituye ``path`` por ``text`` de forma atómica."""
    partial = path.with_name(path.name + ".nuevo")
    try:
        partial.write_text(text, encoding="utf-8")
        partial.replace(path)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise AtrilError(f"no se puede escribir {path}: {exc}") from exc
