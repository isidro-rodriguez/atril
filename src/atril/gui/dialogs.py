"""Ventanas emergentes: centradas, fijas y con el resto de la ventana oscurecido.

Un velo negro semitransparente cubre la ventana principal y encima aparece el
diálogo, sin barra de título (no se puede mover) y con el foco retenido hasta
que se cierra. Todos los mensajes de la ventana usan este patrón. Donde el
sistema no admite transparencia, el velo se omite.
"""

import contextlib
import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from atril.checks import Level
from atril.gui import style

VEIL_ALPHA = 0.35
"""Opacidad del velo que oscurece la ventana."""

WRAP = 440
"""Anchura del texto de los diálogos a 100 %."""


class Modal(tk.Toplevel):
    """Diálogo modal sobre un velo; :meth:`wait` devuelve el resultado."""

    def __init__(self, parent: tk.Misc, title: str, level: Level | None = None) -> None:
        """Crea el velo y la tarjeta del diálogo con su título."""
        self._owner = parent.winfo_toplevel()
        self._veil = _veil(self._owner)
        super().__init__(self._owner, background=style.BORDER)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(self._owner)
        self.result: object = None
        self.body = tk.Frame(self, background=style.CARD, padx=24, pady=20)
        self.body.pack(padx=1, pady=1)
        self.body.columnconfigure(0, weight=1)
        head = style.label(self.body, f"  {title}" if level else title)
        head.configure(font=style.SUBTITLE)
        if level is not None:
            head.configure(image=style.icon(self, style.LEVEL_ICONS[level], 22))
            head.configure(compound="left")
        head.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.bind("<Escape>", lambda _: self.close(None))
        self.wrap = round(WRAP * style.scale(self))

    def text(self, row: int, text: str, color: str = style.TEXT) -> tk.Label:
        """Párrafo del diálogo en la fila ``row``."""
        label = style.label(self.body, text, wraplength=self.wrap, color=color)
        label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
        return label

    def buttons(
        self,
        row: int,
        options: list[tuple[str, object]],
        accent: object = None,
    ) -> dict[object, ttk.Button]:
        """Botones al pie, de izquierda a derecha; ``accent`` resalta uno."""
        bar = tk.Frame(self.body, background=style.CARD)
        bar.grid(row=row, column=0, columnspan=2, sticky="e", pady=(14, 0))
        made = {}
        for column, (text, value) in enumerate(options):
            button = ttk.Button(
                bar,
                text=text,
                style="Accent.TButton" if value == accent else "TButton",
                command=lambda v=value: self.close(v),
            )
            button.grid(row=0, column=column, padx=(8 if column else 0, 0))
            made[value] = button
        return made

    def close(self, value: object) -> None:
        """Cierra con ``value`` como resultado."""
        self.result = value
        self.destroy()

    def wait(self) -> object:
        """Muestra el diálogo centrado, espera a que se cierre y quita el velo."""
        self.update_idletasks()
        x = (
            self._owner.winfo_rootx()
            + (self._owner.winfo_width() - self.winfo_reqwidth()) // 2
        )
        y = (
            self._owner.winfo_rooty()
            + (self._owner.winfo_height() - self.winfo_reqheight()) // 2
        )
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.lift()
        with contextlib.suppress(tk.TclError):
            self.grab_set()
        self.focus_force()
        try:
            self.wait_window()
        finally:
            if self._veil is not None:
                self._veil.destroy()
        return self.result


def _veil(root: tk.Misc) -> tk.Toplevel | None:
    """Velo semitransparente sobre la ventana (``None`` si no se puede)."""
    if sys.platform not in {"win32", "darwin"} or not root.winfo_viewable():
        return None  # sin compositor, X11 pintaría el velo opaco
    veil = tk.Toplevel(root, background="#000000")
    veil.overrideredirect(True)
    try:
        veil.attributes("-alpha", VEIL_ALPHA)
    except tk.TclError:
        veil.destroy()
        return None
    veil.geometry(
        f"{root.winfo_width()}x{root.winfo_height()}"
        f"+{root.winfo_rootx()}+{root.winfo_rooty()}"
    )
    veil.transient(root.winfo_toplevel())
    veil.lift(root)
    return veil


# --- diálogos de uso común ------------------------------------------------------


def show_message(
    parent: tk.Misc, title: str, text: str, level: Level = Level.INFO
) -> None:
    """Mensaje con un botón Aceptar."""
    dialog = Modal(parent, title, level)
    dialog.text(1, text)
    dialog.buttons(2, [("Aceptar", True)], accent=True)
    dialog.wait()


def ask_yes_no(
    parent: tk.Misc,
    title: str,
    text: str,
    accept: str = "Aceptar",
    *,
    level: Level | None = None,
    danger: bool = False,
) -> bool:
    """Confirmación; ``danger`` deja sin resaltar el botón que acepta."""
    dialog = Modal(parent, title, level)
    dialog.text(1, text)
    dialog.buttons(
        2, [("Cancelar", False), (accept, True)], accent=None if danger else True
    )
    return dialog.wait() is True


def ask_three(parent: tk.Misc, title: str, text: str, yes: str, no: str) -> bool | None:
    """Sí, no o cancelar: ``True``, ``False`` o ``None``."""
    dialog = Modal(parent, title, Level.INFO)
    dialog.text(1, text)
    dialog.buttons(2, [("Cancelar", None), (no, False), (yes, True)], accent=True)
    value = dialog.wait()
    return value if isinstance(value, bool) else None


def ask_text(parent: tk.Misc, title: str, prompt: str, initial: str = "") -> str | None:
    """Pedir un texto; ``None`` si se cancela."""
    dialog = Modal(parent, title)
    dialog.text(1, prompt)
    value = tk.StringVar(dialog, initial)
    entry = ttk.Entry(dialog.body, textvariable=value, width=48)
    entry.grid(row=2, column=0, columnspan=2, sticky="ew")
    entry.bind("<Return>", lambda _: dialog.close(True))
    dialog.buttons(3, [("Cancelar", False), ("Aceptar", True)], accent=True)
    dialog.after_idle(entry.focus_set)
    return value.get().strip() if dialog.wait() is True else None


def ask_choice(
    parent: tk.Misc, title: str, prompt: str, options: list[tuple[str, str]]
) -> str | None:
    """Elegir uno de ``options`` (valor, texto visible); ``None`` si se cancela."""
    dialog = Modal(parent, title)
    dialog.text(1, prompt)
    labels = [label for _, label in options]
    choice = tk.StringVar(dialog, labels[0] if labels else "")
    ttk.Combobox(
        dialog.body, textvariable=choice, values=labels, state="readonly", width=44
    ).grid(row=2, column=0, columnspan=2, sticky="ew")
    dialog.buttons(3, [("Cancelar", False), ("Aceptar", True)], accent=True)
    if dialog.wait() is not True:
        return None
    return next(value for value, label in options if label == choice.get())


def confirm_delete(
    parent: tk.Misc, name: str, summary: str, open_folder: Callable[[], None]
) -> bool:
    """Doble confirmación para borrar un temario para siempre.

    La primera explica lo que se pierde y ofrece abrir la carpeta para guardar
    lo que interese; la segunda exige escribir el nombre del temario.
    """
    first = Modal(parent, "Borrar temario", Level.WARNING)
    first.text(
        1,
        f"Se borrará para siempre «{name}»: {summary}. También se borran sus "
        "bases de conocimiento en DeepTutor. No se puede deshacer.",
    )
    first.text(
        2,
        "Si quieres conservar algo (tus PDF, notas o evaluaciones), cópialo antes "
        "o haz un backup.",
        color=style.MUTED,
    )
    first.buttons(
        3, [("Abrir carpeta", "open"), ("Cancelar", False), ("Continuar", True)]
    )
    answer = first.wait()
    if answer == "open":
        open_folder()
        return False
    if answer is not True:
        return False

    second = Modal(parent, "Confirmar el borrado", Level.ERROR)
    second.text(1, f"Escribe el nombre del temario para borrarlo: {name}")
    typed = tk.StringVar(second)
    entry = ttk.Entry(second.body, textvariable=typed, width=48)
    entry.grid(row=2, column=0, columnspan=2, sticky="ew")
    buttons = second.buttons(3, [("Cancelar", False), ("Borrar para siempre", True)])
    delete = buttons[True]
    delete.state(["disabled"])
    typed.trace_add(
        "write",
        lambda *_: delete.state(
            ["!disabled"] if typed.get().strip() == name else ["disabled"]
        ),
    )
    second.after_idle(entry.focus_set)
    return second.wait() is True and typed.get().strip() == name
