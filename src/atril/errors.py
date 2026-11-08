"""Error base de atril, con mensaje en español para el usuario.

La CLI lo muestra en rojo y termina con código 1; la GUI, en un diálogo. Los
errores de cada módulo (``ConfigError``, ``BackupError``, ``StepError``...)
derivan de él.
"""

from collections.abc import Sequence


class AtrilError(Exception):
    """Error que se muestra al usuario tal cual, opcionalmente con un extracto de log.

    Args:
        message: Mensaje en español.
        log: Últimas líneas de un log que ayudan a diagnosticar el error.
        log_title: Origen del extracto (normalmente, la ruta del log).
    """

    def __init__(
        self, message: str, log: Sequence[str] = (), log_title: str = ""
    ) -> None:
        """Guarda el mensaje y el extracto de log."""
        super().__init__(message)
        self.log = tuple(log)
        self.log_title = log_title


class CancelledError(AtrilError):
    """El usuario ha cancelado la operación en un punto seguro."""
