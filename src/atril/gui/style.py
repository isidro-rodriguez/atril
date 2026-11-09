"""Tema, colores, tipografía e imágenes de la GUI, en un solo sitio.

Base: tema Sun Valley (``sv-ttk``, aspecto de Windows 11) en claro, con la paleta
azul del logotipo y la fuente Inter incluida en el paquete. Los textos y fondos
propios van en widgets ``tk`` (:func:`label`): ``sv-ttk`` recolorea con
``tk_setPalette`` y en algunas versiones de Tk pisa los colores de ``ttk.Label``.
"""

import contextlib
import sys
import tkinter as tk
import tkinter.font as tkfont
from importlib import resources
from importlib.resources.abc import Traversable
from tkinter import ttk

import sv_ttk

from atril.checks import Level

PAGE = "#e9eff8"
"""Fondo general, el mismo de la navegación (azul grisáceo muy claro)."""
SIDEBAR = PAGE
"""Fondo de la navegación y del pie de ventana."""
CARD = "#ffffff"
"""Fondo de las tarjetas."""
BORDER = "#dfe5ee"
"""Bordes y separadores."""
SELECTED = "#d6e6fb"
"""Fondo del apartado activo."""
ACCENT = "#0f5ec9"
"""Color principal (azul)."""
TEXT = "#14254a"
"""Texto principal (azul marino oscuro)."""
NAVY = "#14254a"
"""Títulos (alias de :data:`TEXT`)."""
MUTED = "#5b6b85"
"""Texto secundario."""
HERO = "#f4f8fe"
"""Fondo del «Estado general» de Inicio: el bloque principal de la ventana."""
FIELD = "#fafafa"
"""Fondo de las tablas de sv-ttk y de los recuadros de texto."""
TEXT_SELECTION = "#e7e7e7"
"""Fondo del texto seleccionado (el de las filas elegidas de las tablas)."""
TEXT_SELECTED = "#191919"
"""Color del texto seleccionado."""

LEVEL_COLORS = {
    Level.OK: "#1a8f3c",
    Level.INFO: ACCENT,
    Level.WARNING: "#b45f06",
    Level.ERROR: "#c42b1c",
}
"""Color de cada nivel (verde, azul, naranja, rojo)."""

LEVEL_ICONS = {
    Level.OK: "circle-check-ok",
    Level.INFO: "info-info",
    Level.WARNING: "triangle-alert-aviso",
    Level.ERROR: "circle-x-error",
}
"""Icono de cada nivel: el estado nunca depende solo del color."""

LEVEL_SYMBOLS = {
    Level.OK: "•",
    Level.INFO: "·",
    Level.WARNING: "!",
    Level.ERROR: "\u00d7",  # signo de multiplicación
}
"""Símbolo de cada nivel en textos (en la fuente incluida; ✓ y ✗ no están)."""


def tag_levels(tree: ttk.Treeview) -> None:
    """Etiquetas de nivel de una tabla: solo avisos y errores llevan color."""
    for level in (Level.WARNING, Level.ERROR):
        tree.tag_configure(level.value, foreground=LEVEL_COLORS[level])


BODY = "AtrilBody"
SMALL = "AtrilSmall"
STRONG = "AtrilStrong"
NAV = "AtrilNav"
SUBTITLE = "AtrilSubtitle"
TITLE = "AtrilTitle"
LEAD = "AtrilLead"
DISPLAY = "AtrilDisplay"
CAPTION = SMALL
"""Fuentes con nombre de atril (ver :func:`_fonts`)."""

FONT_FILES = ("Inter-Regular.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")
"""Fuentes incluidas en el paquete (OFL)."""

CARD_BORDER = 11
"""Borde 9-slice de la imagen de tarjeta a 100 % (radio + 1)."""

_RESOURCES = resources.files("atril.gui") / "recursos"


def register_fonts() -> None:
    """Registra Inter solo para este proceso (Windows), antes de crear la ventana.

    En otros sistemas no hace nada: se usa la fuente del sistema.
    """
    if sys.platform != "win32":
        return
    import ctypes

    private = 0x10  # FR_PRIVATE: solo atril la ve; no se instala en el sistema
    for name in FONT_FILES:
        with (
            resources.as_file(_RESOURCES / "fuentes" / name) as path,
            contextlib.suppress(AttributeError, OSError),
        ):
            ctypes.windll.gdi32.AddFontResourceExW(str(path), private, 0)


def apply(root: tk.Tk) -> None:
    """Tema claro de Sun Valley, fuentes y estilos de atril.

    ``sv-ttk`` recolorea con ``tk_setPalette`` al procesar ``<<ThemeChanged>>``:
    se procesa aquí, antes de crear los widgets, para que no pise sus fondos.
    """
    sv_ttk.set_theme("light", root)
    root.update()
    root.configure(background=PAGE)
    _fonts(root)
    style = ttk.Style(root)
    for name, element in (
        ("tarjeta", "Atril.Card.bg"),
        ("campo", "Atril.Field.bg"),
        ("destacado", "Atril.Hero.bg"),
    ):
        image = tk.PhotoImage(
            master=root,
            data=_resource(f"{name}{'@2x' if scale(root) >= 1.75 else ''}.png"),
        )
        border = CARD_BORDER * (2 if scale(root) >= 1.75 else 1)
        _images[(name, border)] = image  # que no se libere
        style.element_create(element, "image", image, border=border, sticky="nsew")
    style.layout("Card.Atril.TFrame", [("Atril.Card.bg", {"sticky": "nsew"})])
    style.configure("Card.Atril.TFrame", background=PAGE)
    # La misma tarjeta dentro de otra (esquinas sobre blanco): baldosas y recuadros.
    style.layout("Tile.Atril.TFrame", [("Atril.Card.bg", {"sticky": "nsew"})])
    style.configure("Tile.Atril.TFrame", background=CARD)
    # Recuadro con el fondo de las tablas para textos largos (detalle de Actividad).
    style.layout("Field.Atril.TFrame", [("Atril.Field.bg", {"sticky": "nsew"})])
    style.configure("Field.Atril.TFrame", background=CARD)
    # Bloque destacado de Inicio y sus recuadros blancos (esquinas sobre HERO).
    style.layout("Hero.Atril.TFrame", [("Atril.Hero.bg", {"sticky": "nsew"})])
    style.configure("Hero.Atril.TFrame", background=PAGE)
    style.layout("HeroTile.Atril.TFrame", [("Atril.Card.bg", {"sticky": "nsew"})])
    style.configure("HeroTile.Atril.TFrame", background=HERO)
    for widget in ("TButton", "Accent.TButton", "TCheckbutton", "TEntry", "TCombobox"):
        style.configure(widget, font=BODY)
    style.configure("Treeview", font=BODY, rowheight=round(28 * scale(root)))
    em = round(13 * scale(root))  # 1 em de BODY (10 pt) en píxeles
    style.configure("Treeview.Heading", font=STRONG, padding=(em, 4))
    # Cada «style configure» programa otro <<ThemeChanged>> y sv-ttk vuelve a
    # aplicar su paleta: se procesa ya, antes de que existan los widgets.
    root.update()
    root.configure(background=PAGE)


_named_fonts: list[tkfont.Font] = []


def _fonts(root: tk.Tk) -> None:
    """Crea las fuentes con nombre: Inter si está, si no la del sistema."""
    families = set(tkfont.families(root))
    if "Inter" in families:
        body, strong = "Inter", "Inter SemiBold" if "Inter SemiBold" in families else ""
    else:
        body = (
            "Segoe UI"
            if "Segoe UI" in families
            else tkfont.nametofont("TkDefaultFont", root=root).actual("family")
        )
        strong = "Segoe UI Semibold" if "Segoe UI Semibold" in families else ""
    for name, size, semibold in (
        (BODY, 10, False),
        (SMALL, 9, False),
        (STRONG, 10, True),
        (NAV, 11, False),
        (LEAD, 12, False),
        (SUBTITLE, 14, True),
        (TITLE, 18, True),
        (DISPLAY, 30, True),
    ):
        family = strong if semibold and strong else body
        weight = "bold" if semibold and not strong else "normal"
        with contextlib.suppress(tk.TclError):
            tkfont.Font(root, name=name, exists=True).configure(
                family=family, size=size, weight=weight
            )
            continue
        # Hay que conservar el objeto: al liberarse, tkinter borra la fuente con
        # nombre y los widgets vuelven a la fuente por defecto.
        _named_fonts.append(
            tkfont.Font(root, name=name, family=family, size=size, weight=weight)
        )


def scale(root: tk.Misc) -> float:
    """Escala de la pantalla respecto a 96 ppp (1,0 · 1,25 · 1,5...)."""
    return float(root.tk.call("tk", "scaling")) / (96 / 72)


def _resource(name: str) -> bytes:
    """Bytes de un recurso del paquete."""
    path: Traversable = _RESOURCES
    for part in name.split("/"):
        path = path / part
    return path.read_bytes()


CELL_PAD = "   "
"""Sangría de las celdas de las tablas, para alinearlas con el margen de 1 em de
sus cabeceras (``ttk`` no admite margen por celda)."""


def autoscroll(
    widget: ttk.Treeview | tk.Canvas | tk.Text, scrollbar: ttk.Scrollbar
) -> None:
    """Barra de desplazamiento vertical que solo se ve si hace falta."""

    def update(first: str | float, last: str | float) -> None:
        if float(first) <= 0 and float(last) >= 1:
            scrollbar.grid_remove()
        else:
            scrollbar.grid()
        scrollbar.set(first, last)

    widget.configure(yscrollcommand=update)


def cells(*values: object) -> tuple[str, ...]:
    """Valores de una fila de tabla con la sangría de :data:`CELL_PAD`.

    Examples:
        >>> cells("Ley 39/2015", 3)
        ('   Ley 39/2015', '   3')
    """
    return tuple(f"{CELL_PAD}{value}" for value in values)


_images: dict[tuple[str, int], tk.PhotoImage] = {}
_sizes: dict[str, list[int]] = {}


def icon(root: tk.Misc, name: str, base: int = 22) -> tk.PhotoImage:
    """Icono ``nombre-variante`` (p. ej. ``house-nav``) de unos ``base`` px a 100 %.

    Se elige el PNG disponible más cercano a ``base`` por la escala de pantalla
    (se generan a 1x, 1,5x y 2x de su tamaño propio).
    """
    if not _sizes:
        for entry in (_RESOURCES / "iconos").iterdir():
            stem, _, size = entry.name.removesuffix(".png").rpartition("-")
            if size.isdigit():
                _sizes.setdefault(stem, []).append(int(size))
    wanted = base * scale(root)
    size = min(_sizes[name], key=lambda candidate: abs(candidate - wanted))
    key = (name, size)
    if key not in _images:
        _images[key] = tk.PhotoImage(
            master=root, data=_resource(f"iconos/{name}-{size}.png")
        )
    return _images[key]


GENERIC_LOGO = "bot-marca"
"""Icono de las herramientas sin logotipo en ``marcas/`` (el asistente)."""


def brand(root: tk.Misc, name: str, base: int = 36) -> tk.PhotoImage:
    """Logotipo de una herramienta (``marcas/``) al tamaño más cercano a ``base``.

    Sin logotipo propio se usa un icono genérico (:data:`GENERIC_LOGO`).
    """
    wanted = base * scale(root)
    sizes = [
        int(entry.name.removesuffix(".png").rpartition("-")[2])
        for entry in (_RESOURCES / "marcas").iterdir()
        if entry.name.startswith(f"{name}-") and entry.name.endswith(".png")
    ]
    if not sizes:
        return icon(root, GENERIC_LOGO, base)
    size = min(sizes, key=lambda candidate: abs(candidate - wanted))
    key = (f"marca-{name}", size)
    if key not in _images:
        _images[key] = tk.PhotoImage(
            master=root, data=_resource(f"marcas/{name}-{size}.png")
        )
    return _images[key]


def logo(root: tk.Misc, size: int) -> tk.PhotoImage:
    """Logotipo de atril (PNG generado del SVG) al tamaño más cercano."""
    available = (32, 48, 64, 96, 128, 256)
    wanted = size * scale(root)
    chosen = min(available, key=lambda candidate: abs(candidate - wanted))
    key = (f"logo-{chosen}", chosen)
    if key not in _images:
        _images[key] = tk.PhotoImage(master=root, data=_resource(f"logo-{chosen}.png"))
    return _images[key]


def label(
    parent: tk.Misc,
    text: str = "",
    *,
    background: str = CARD,
    font: str = BODY,
    color: str = TEXT,
    padx: int = 0,
    pady: int = 0,
    wraplength: int = 0,
    image: tk.PhotoImage | None = None,
) -> tk.Label:
    """Etiqueta con fuente y colores propios (y un icono a la izquierda)."""
    widget = tk.Label(
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
    if image is not None:
        widget.configure(image=image, compound="left")
    return widget


def tile(
    parent: tk.Misc, padding: tuple[int, int] = (16, 12), field: bool = False
) -> ttk.Frame:
    """Recuadro redondeado con borde fino, para colocar dentro de una tarjeta.

    Con ``field`` tiene el fondo de las tablas (:data:`FIELD`) en vez de blanco.
    """
    factor = scale(parent)
    return ttk.Frame(
        parent,
        style="Field.Atril.TFrame" if field else "Tile.Atril.TFrame",
        padding=(round(padding[0] * factor), round(padding[1] * factor)),
    )


def hero(parent: tk.Misc) -> ttk.Frame:
    """Bloque destacado (fondo :data:`HERO`, borde azul claro y esquinas redondeadas).

    Es el elemento principal de Inicio: más aire que una tarjeta normal.
    """
    factor = scale(parent)
    return ttk.Frame(
        parent,
        style="Hero.Atril.TFrame",
        padding=(round(28 * factor), round(22 * factor)),
    )


def card(parent: tk.Misc, title: str = "") -> ttk.Frame:
    """Tarjeta blanca con esquinas redondeadas y título en la fila 0.

    Los hijos se colocan directamente en ella (fondo :data:`CARD`).
    """
    factor = scale(parent)
    frame = ttk.Frame(
        parent,
        style="Card.Atril.TFrame",
        padding=(round(20 * factor), round(16 * factor)),
    )
    if title:
        label(frame, title, font=SUBTITLE).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )
    return frame
