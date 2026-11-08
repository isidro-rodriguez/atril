"""Tema, colores y tipografía de la GUI, en un solo sitio.

Se usa el tema Sun Valley (``sv-ttk``, aspecto de Windows 11) en claro, con la
paleta azul del icono de atril.
"""

import tkinter as tk

import sv_ttk

from atril.checks import Level

CARD = "#fafafa"
"""Fondo de las tarjetas: el del tema, para que botones y barras encajen."""
PAGE = "#f0f3f8"
"""Fondo de la zona de contenido, entre tarjetas."""
BORDER = "#dfe5ee"
"""Borde de las tarjetas."""
SIDEBAR = "#e8eff9"
"""Fondo de la barra lateral y de la barra de estado."""
BANNER = "#dde9fb"
"""Fondo de la cabecera."""
SELECTED = "#c9dcf8"
"""Fondo del apartado activo de la barra lateral."""
TEXT = "#1c1c1c"
"""Texto normal (el del tema)."""
NAVY = "#0b2d6b"
"""Títulos (azul del birrete)."""
BLUE = "#1f5fbf"
"""Lema."""
MUTED = "#5f6b7a"
"""Texto secundario."""

LEVEL_COLORS = {
    Level.OK: "#0f7b0f",
    Level.INFO: "#5f6b7a",
    Level.WARNING: "#9d5d00",
    Level.ERROR: "#c42b1c",
}
"""Color de cada nivel de comprobación (paleta de estados de Windows 11)."""

LEVEL_SYMBOLS = {Level.OK: "✓", Level.INFO: "·", Level.WARNING: "!", Level.ERROR: "✗"}
"""Símbolo de cada nivel, igual que en la CLI."""

BODY = "SunValleyBodyFont"
STRONG = "SunValleyBodyStrongFont"
CAPTION = "SunValleyCaptionFont"
SUBTITLE = "SunValleySubtitleFont"
TITLE = "SunValleyTitleLargeFont"
"""Fuentes con nombre que define ``sv-ttk``."""


def apply(root: tk.Tk) -> None:
    """Aplica el tema claro de Sun Valley.

    Los textos y fondos propios van en widgets ``tk`` (:func:`label`,
    :func:`card`): con ``sv-ttk`` los colores de los estilos de ``ttk.Label`` no
    se respetan en todas las versiones de Tk.
    """
    sv_ttk.set_theme("light", root)
    # sv-ttk recolorea con tk_setPalette al procesar <<ThemeChanged>>: se procesa
    # ya, antes de crear los widgets, para que no pise sus fondos.
    root.update()
    root.configure(background=PAGE)


def label(
    parent: tk.Misc,
    text: str = "",
    *,
    background: str,
    font: str = BODY,
    color: str = TEXT,
    padx: int = 0,
    pady: int = 0,
    wraplength: int = 0,
) -> tk.Label:
    """Etiqueta con fuente y colores propios."""
    return tk.Label(
        parent,
        text=text,
        background=background,
        foreground=color,
        font=font,
        anchor="w",
        justify="left",
        padx=padx,
        pady=pady,
        wraplength=wraplength,
    )


def card(parent: tk.Misc, title: str) -> tk.Frame:
    """Tarjeta con borde fino y título; el contenido va de la fila 1 en adelante."""
    frame = tk.Frame(
        parent,
        background=CARD,
        highlightthickness=1,
        highlightbackground=BORDER,
        padx=18,
        pady=14,
    )
    label(frame, title, background=CARD, font=SUBTITLE, color=NAVY).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
    )
    return frame
