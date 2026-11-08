"""Casos de uso de atril, compartidos por la CLI y la GUI.

No imprimen ni terminan el proceso: devuelven resultados o
:class:`~atril.checks.Finding`, informan del avance a un :class:`Reporter` y
lanzan :class:`~atril.errors.AtrilError` con el mensaje para el usuario. Las
confirmaciones las pide la interfaz antes de llamarlos.
"""

import contextlib
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from atril.checks import Finding

Advance = Callable[[int], None]
"""Suma unidades (bytes, ficheros...) a la barra de avance."""

Update = Callable[[str], None]
"""Cambia el texto de una espera en curso (p. ej. minutos y fase del indexado)."""


class Reporter(Protocol):
    """Destino del avance de una operación: consola Rich, ventana o nada."""

    def show(self, findings: Sequence[Finding], title: str | None = None) -> None:
        """Muestra comprobaciones, con un título de sección opcional."""
        ...

    def busy(self, text: str) -> AbstractContextManager[Update]:
        """Indica una espera sin avance medible; devuelve con qué cambiar su texto."""
        ...

    def progress(self, text: str, total: int) -> AbstractContextManager[Advance]:
        """Indica un trabajo de ``total`` unidades; devuelve con qué avanzar."""
        ...


class Recorder:
    """Reporter que solo guarda lo recibido: pruebas y trabajos sin interfaz."""

    def __init__(self) -> None:
        """Empieza sin comprobaciones ni pasos."""
        self.findings: list[Finding] = []
        self.steps: list[str] = []

    def show(self, findings: Sequence[Finding], title: str | None = None) -> None:
        """Guarda las comprobaciones."""
        self.findings.extend(findings)

    @contextlib.contextmanager
    def busy(self, text: str) -> Generator[Update]:
        """Guarda el texto de la espera y sus cambios."""
        self.steps.append(text)
        yield self.steps.append

    @contextlib.contextmanager
    def progress(self, text: str, total: int) -> Generator[Advance]:
        """Guarda el texto y descarta el avance."""
        self.steps.append(text)
        yield lambda amount: None
