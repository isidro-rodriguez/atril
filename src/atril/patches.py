"""Parches locales de atril sobre el código de DeepTutor (``app/``).

Cada parche es una sustitución de texto idempotente en un fichero: si el texto
nuevo ya está, el parche está aplicado; si está el original, se puede aplicar;
si no está ninguno, el código de DeepTutor ha cambiado y hay que revisarlo.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PatchState(StrEnum):
    """Estado de un parche sobre el checkout."""

    APPLIED = "aplicado"
    PENDING = "pendiente"
    CHANGED = "código cambiado"
    """No aparece ni el texto original ni el parcheado: hay que revisar el parche."""
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
        if self.new in text:
            return PatchState.APPLIED
        if self.old in text:
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
