"""Resultados de comprobaciones que los comandos muestran al usuario."""

from dataclasses import dataclass
from enum import StrEnum


class Level(StrEnum):
    """Gravedad de una comprobación."""

    OK = "ok"
    INFO = "info"
    WARNING = "aviso"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Finding:
    """Resultado de una comprobación, con su mensaje en español."""

    level: Level
    message: str


def ok(message: str) -> Finding:
    """Comprobación superada."""
    return Finding(Level.OK, message)


def info(message: str) -> Finding:
    """Dato informativo, sin valoración."""
    return Finding(Level.INFO, message)


def warning(message: str) -> Finding:
    """Situación que conviene revisar pero no impide continuar."""
    return Finding(Level.WARNING, message)


def error(message: str) -> Finding:
    """Situación que impide funcionar correctamente."""
    return Finding(Level.ERROR, message)
