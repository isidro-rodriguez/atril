"""Parches locales de atril sobre el código de DeepTutor (``app/``).

Cada parche es una sustitución de texto idempotente en un fichero. Solo se
reconocen dos estados limpios: el original una vez y el nuevo ninguna
(pendiente), o al revés (aplicado). Cualquier otra combinación (ninguno, ambos
o repetidos) significa que el código de DeepTutor ha cambiado y hay que revisar
el parche; nunca se fuerza.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PatchState(StrEnum):
    """Estado de un parche sobre el checkout."""

    APPLIED = "aplicado"
    PENDING = "pendiente"
    CHANGED = "código cambiado"
    """El texto original y el parcheado no aparecen una sola vez: hay que revisarlo."""
    NO_FILE = "sin fichero"


@dataclass(frozen=True, slots=True)
class Patch:
    """Sustitución de ``old`` por ``new`` en ``file`` (relativo a ``app/``)."""

    name: str
    description: str
    file: str
    old: str
    new: str

    def state(self, app_dir: Path) -> PatchState:
        """Estado del parche en el checkout ``app_dir``."""
        path = app_dir / self.file
        if not path.is_file():
            return PatchState.NO_FILE
        text = _read(path)
        new = text.count(self.new)
        # Si ``new`` contiene ``old``, sus apariciones no cuentan como originales.
        old = text.replace(self.new, "").count(self.old)
        if (old, new) == (0, 1):
            return PatchState.APPLIED
        if (old, new) == (1, 0):
            return PatchState.PENDING
        return PatchState.CHANGED

    def apply(self, app_dir: Path) -> PatchState:
        """Aplica el parche si está pendiente.

        Returns:
            El estado final: ``APPLIED`` si ya lo estaba o se ha aplicado; si no,
            ``CHANGED`` o ``NO_FILE`` (no se toca nada).
        """
        state = self.state(app_dir)
        if state is PatchState.PENDING:
            path = app_dir / self.file
            path.write_bytes(_read(path).replace(self.old, self.new, 1).encode("utf-8"))
            return PatchState.APPLIED
        return state

    def revert(self, app_dir: Path) -> PatchState:
        """Deshace el parche si está aplicado (antes de actualizar con git).

        Returns:
            El estado final: ``PENDING`` si se ha deshecho o ya lo estaba; si no,
            ``CHANGED`` o ``NO_FILE`` (no se toca nada).
        """
        state = self.state(app_dir)
        if state is PatchState.APPLIED:
            path = app_dir / self.file
            path.write_bytes(_read(path).replace(self.new, self.old, 1).encode("utf-8"))
            return PatchState.PENDING
        return state


def _read(path: Path) -> str:
    """Lee en UTF-8 conservando los finales de línea originales."""
    return path.read_bytes().decode("utf-8")


PATCHES: dict[str, Patch] = {
    patch.name: patch
    for patch in (
        Patch(
            name="paginas-citas",
            description="Citas de LlamaIndex con página: usa 'page' si 'page_label' "
            "está vacío.",
            file="deeptutor/services/rag/pipelines/llamaindex/pipeline.py",
            old='"page": meta.get("page_label", meta.get("page", "")),',
            new='"page": meta.get("page_label") or meta.get("page", ""),',
        ),
    )
}
"""Parches disponibles, por nombre (el que se usa en ``[deeptutor] parches``)."""
