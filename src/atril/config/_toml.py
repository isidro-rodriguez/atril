"""Lectura estricta de ficheros TOML con mensajes de error en español."""

import tomllib
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Any, cast

from acodo.utils import has_only_keys


class ConfigError(Exception):
    """Error en un fichero de configuración (``atril.toml`` o ``temario.toml``).

    El mensaje indica el fichero y, si procede, la tabla y la clave afectadas.
    """


_MISSING: Any = object()


def load_toml(path: Path) -> dict[str, Any]:
    """Carga un fichero TOML.

    Raises:
        ConfigError: Si el fichero no existe, no puede leerse o no es TOML válido.
    """
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"No existe el fichero {path}.") from exc
    except OSError as exc:
        raise ConfigError(f"No se puede leer {path}: {exc}.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: TOML no válido: {exc}.") from exc


class Table:
    """Vista de una tabla TOML que valida tipos y rechaza claves desconocidas.

    Cada clave leída se registra; :meth:`close` falla si queda alguna sin leer,
    para detectar erratas en la configuración.
    """

    def __init__(self, data: dict[str, Any], source: Path, where: str = "") -> None:
        """Envuelve ``data``; ``where`` identifica la tabla en los mensajes."""
        self._data = data
        self._source = source
        self._where = where
        self._used: set[str] = set()

    def error(self, message: str) -> ConfigError:
        """Crea un :class:`ConfigError` situado en esta tabla."""
        place = f" {self._where}" if self._where else ""
        return ConfigError(f"{self._source}{place}: {message}")

    def _get(self, key: str, kind: type, default: Any) -> Any:
        """Devuelve ``key`` comprobando su tipo, o ``default`` si falta."""
        self._used.add(key)
        if key not in self._data:
            if default is _MISSING:
                raise self.error(f"falta la clave obligatoria '{key}'.")
            return default
        value = self._data[key]
        # bool es subclase de int: no se acepta donde se espera un número.
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise self.error(f"'{key}' tiene un valor de tipo no válido: {value!r}.")
        return value

    def get_str(self, key: str, default: Any = _MISSING) -> Any:
        """Texto no vacío (o ``default`` si falta)."""
        value = self._get(key, str, default)
        if isinstance(value, str) and not value.strip():
            raise self.error(f"'{key}' no puede estar vacío.")
        return value

    def get_int(self, key: str, default: int = _MISSING, *, minimum: int = 1) -> int:
        """Entero mayor o igual que ``minimum``."""
        value: int = self._get(key, int, default)
        if value < minimum:
            raise self.error(f"'{key}' debe ser >= {minimum} (vale {value}).")
        return value

    def get_bool(self, key: str, default: bool = _MISSING) -> bool:
        """Booleano."""
        return self._get(key, bool, default)

    def get_str_list(self, key: str, default: list[str] = _MISSING) -> list[str]:
        """Lista de textos no vacíos."""
        value = self._get(key, list, default)
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise self.error(f"'{key}' debe ser una lista de textos no vacíos.")
        return list(value)

    def get_table(self, key: str, *, required: bool = True) -> "Table":
        """Subtabla ``key``; vacía si falta y no es obligatoria."""
        value = self._get(key, dict, _MISSING if required else {})
        inner = self._where.strip("[]")
        return Table(value, self._source, f"[{inner}.{key}]" if inner else f"[{key}]")

    def get_named_tables(self) -> list[tuple[str, "Table"]]:
        """Todas las claves como subtablas (tablas con nombres libres)."""
        return [(key, self.get_table(key)) for key in self._data]

    def get_table_list(self, key: str) -> list["Table"]:
        """Array de tablas ``[[key]]``; lista vacía si falta."""
        value = self._get(key, list, [])
        if not all(isinstance(item, dict) for item in value):
            raise self.error(f"'{key}' debe declararse como [[{key}]].")
        return [
            Table(item, self._source, f"[[{key}]] n.º {n}")
            for n, item in enumerate(value, 1)
        ]

    def close(self) -> None:
        """Falla si la tabla contiene claves que no se han leído."""
        # cast: Mapping es invariante en la clave y acodo 0.5 declara
        # Mapping[Hashable, Any], que no admite dict[str, Any] en ty.
        data = cast("Mapping[Hashable, Any]", self._data)
        if not has_only_keys(data, self._used):
            unknown = sorted(set(self._data) - self._used)
            raise self.error(f"claves desconocidas: {', '.join(unknown)}.")
