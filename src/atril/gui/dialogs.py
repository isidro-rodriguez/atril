"""Diálogos propios: elegir de una lista y confirmar el borrado de un temario."""

import tkinter as tk
from tkinter import ttk

from atril.gui import style


class _Dialog(tk.Toplevel):
    """Diálogo modal con fondo de tarjeta y botones Aceptar/Cancelar."""

    def __init__(self, parent: tk.Misc, title: str) -> None:
        """Prepara la ventana modal sobre ``parent``."""
        super().__init__(parent, background=style.CARD, padx=22, pady=18)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.accepted = False

    def buttons(self, row: int, accept: str = "Aceptar", danger: bool = False) -> None:
        """Botones al pie; ``danger`` deja Aceptar sin resaltar."""
        bar = tk.Frame(self, background=style.CARD)
        bar.grid(row=row, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(bar, text="Cancelar", command=self.destroy).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(
            bar,
            text=accept,
            style="TButton" if danger else "Accent.TButton",
            command=self._accept,
        ).grid(row=0, column=1)

    def _accept(self) -> None:
        """Acepta y cierra."""
        self.accepted = True
        self.destroy()

    def wait(self) -> bool:
        """Espera a que se cierre; ``True`` si se aceptó."""
        self.grab_set()
        self.wait_window()
        return self.accepted


def ask_choice(
    parent: tk.Misc, title: str, prompt: str, options: list[tuple[str, str]]
) -> str | None:
    """Elegir uno de ``options`` (valor, texto visible); ``None`` si se cancela."""
    dialog = _Dialog(parent, title)
    style.label(dialog, prompt).grid(row=0, column=0, columnspan=2, sticky="w")
    labels = [label for _, label in options]
    choice = tk.StringVar(parent, labels[0] if labels else "")
    ttk.Combobox(
        dialog, textvariable=choice, values=labels, state="readonly", width=40
    ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    dialog.buttons(2)
    if not dialog.wait():
        return None
    return next(value for value, label in options if label == choice.get())


def ask_text(parent: tk.Misc, title: str, prompt: str, initial: str = "") -> str | None:
    """Pedir un texto; ``None`` si se cancela."""
    dialog = _Dialog(parent, title)
    style.label(dialog, prompt).grid(row=0, column=0, columnspan=2, sticky="w")
    value = tk.StringVar(parent, initial)
    entry = ttk.Entry(dialog, textvariable=value, width=46)
    entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    entry.focus_set()
    entry.bind("<Return>", lambda _: dialog._accept())
    dialog.buttons(2)
    return value.get().strip() if dialog.wait() else None


def confirm_delete(parent: tk.Misc, name: str, kbs: list[str]) -> bool | None:
    """Confirma eliminar un temario.

    Returns:
        ``None`` si se cancela; si no, si hay que borrar también sus KB.
    """
    dialog = _Dialog(parent, "Eliminar temario")
    style.label(
        dialog,
        f"«{name}» irá a la papelera de temarios (temarios/.papelera): sus ficheros "
        "no se borran y se puede recuperar moviendo la carpeta.",
        wraplength=420,
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    remove_kbs = tk.BooleanVar(parent, value=False)
    ttk.Checkbutton(
        dialog,
        text=f"Borrar también de DeepTutor sus KB ({', '.join(kbs)}). No se puede "
        "deshacer.",
        variable=remove_kbs,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))
    dialog.buttons(2, "Eliminar", danger=True)
    return remove_kbs.get() if dialog.wait() else None
