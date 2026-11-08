"""Componentes de la ventana: navegación, pie de ventana y baldosas de herramientas.

Pocos y concretos: cada uno se usa en varios sitios o aísla una parte de la
ventana. La lógica de presentación sin Tk está en :mod:`atril.gui.model`.
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from atril import __version__
from atril.checks import Level
from atril.gui import style
from atril.gui.model import Action, ToolCard

SIDEBAR_WIDTH = 200
"""Anchura de la navegación a 100 % (se escala con la pantalla)."""


class Sidebar(tk.Frame):
    """Navegación lateral: logotipo y nombre arriba, un apartado por fila."""

    def __init__(self, parent: tk.Misc, on_select: Callable[[str], None]) -> None:
        """Construye logotipo y nombre; los apartados se añaden con :meth:`add`."""
        width = round(SIDEBAR_WIDTH * style.scale(parent))
        super().__init__(parent, background=style.SIDEBAR, width=width)
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self._on_select = on_select
        self._items: dict[str, tuple[tk.Frame, tk.Label, str]] = {}
        tk.Label(self, image=style.logo(self, 72), background=style.SIDEBAR).grid(
            row=0, column=0, pady=(20, 4)
        )
        name = style.label(self, "Atril", background=style.SIDEBAR, font=style.TITLE)
        name.configure(anchor="center")
        name.grid(row=1, column=0, pady=(0, 20))

    def add(self, name: str, icon: str) -> None:
        """Añade un apartado con su icono de Lucide (sin variante)."""
        row = len(self._items) + 2
        item = tk.Frame(self, background=style.SIDEBAR, cursor="hand2")
        item.grid(row=row, column=0, sticky="ew", padx=(10, 0), pady=2)
        item.columnconfigure(1, weight=1)
        marker = tk.Frame(item, background=style.SIDEBAR, width=4)
        marker.grid(row=0, column=0, sticky="ns")
        text = style.label(
            item,
            f"  {name}",
            background=style.SIDEBAR,
            font=style.NAV,
            image=style.icon(self, f"{icon}-nav"),
            padx=12,
            pady=8,
        )
        text.grid(row=0, column=1, sticky="ew")
        for widget in (item, text, marker):
            widget.bind("<Button-1>", lambda _, n=name: self._on_select(n))
        self._items[name] = (item, text, icon)

    def select(self, name: str) -> None:
        """Marca el apartado activo (fondo azul claro e indicador lateral)."""
        for key, (item, text, icon) in self._items.items():
            active = key == name
            background = style.SELECTED if active else style.SIDEBAR
            item.configure(background=background)
            text.configure(
                background=background,
                foreground=style.ACCENT if active else style.TEXT,
                image=style.icon(self, f"{icon}-{'sel' if active else 'nav'}"),
            )
            marker = item.grid_slaves(row=0, column=0)[0]
            marker["background"] = style.ACCENT if active else background


class Footer(tk.Frame):
    """Pie de ventana: estado de los servicios, operación en curso y versión."""

    def __init__(self, parent: tk.Misc) -> None:
        """Construye las tres zonas."""
        super().__init__(parent, background=style.SIDEBAR, padx=16, pady=6)
        self.columnconfigure(2, weight=1)
        self._services: dict[str, tk.Label] = {}
        for column, name in enumerate(("DeepTutor", "Ollama")):
            label = style.label(
                self, f"  {name}: …", background=style.SIDEBAR, font=style.SMALL
            )
            label.configure(compound="left")
            label.grid(row=0, column=column, sticky="w", padx=(0, 18))
            self._services[name] = label
        self.status = style.label(
            self, "", background=style.SIDEBAR, font=style.SMALL, color=style.MUTED
        )
        self.status.grid(row=0, column=2, sticky="e", padx=(0, 10))
        self.bar = ttk.Progressbar(self, length=160, mode="indeterminate")
        self.bar.grid(row=0, column=3, sticky="e", padx=(0, 16))
        self.bar.grid_remove()
        style.label(
            self,
            f"v{__version__}",
            background=style.SIDEBAR,
            font=style.SMALL,
            color=style.MUTED,
        ).grid(row=0, column=4, sticky="e")

    def set_service(self, name: str, level: Level, text: str) -> None:
        """Estado de un servicio: icono de nivel y palabra."""
        self._services[name].configure(
            text=f"  {name}: {text}",
            image=style.icon(self, style.LEVEL_ICONS[level], 18),
        )


class ToolTile(tk.Frame):
    """Baldosa de una herramienta: logotipo, nombre, estado y una acción."""

    def __init__(self, parent: tk.Misc, on_action: Callable[[ToolCard], None]) -> None:
        """Construye la baldosa vacía; se rellena con :meth:`show`."""
        super().__init__(
            parent,
            background=style.CARD,
            highlightthickness=1,
            highlightbackground=style.BORDER,
            padx=12,
            pady=10,
        )
        self.columnconfigure(1, weight=1)
        self._on_action = on_action
        self._card: ToolCard | None = None
        self._logo = tk.Label(self, background=style.CARD)
        self._logo.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))
        self._title = style.label(self, "", font=style.STRONG)
        self._title.grid(row=0, column=1, sticky="sw")
        self._state = style.label(
            self,
            "",
            font=style.SMALL,
            color=style.MUTED,
            wraplength=round(110 * style.scale(parent)),
        )
        self._state.grid(row=1, column=1, sticky="nw")
        self._done = tk.Label(self, background=style.CARD)
        self._button = ttk.Button(self, command=self._act, width=8)

    def show(self, card: ToolCard) -> None:
        """Pinta la herramienta y su única acción (o la marca de instalada)."""
        self._card = card
        image = (
            style.brand(self, card.logo)
            if card.logo
            else style.icon(self, "bot-marca", 36)
        )
        self._logo.configure(image=image)
        self._title.configure(text=card.name)
        self._state.configure(
            text=card.state,
            foreground=style.LEVEL_COLORS[card.level]
            if card.level in {Level.WARNING, Level.ERROR}
            else style.MUTED,
        )
        self._done.grid_remove()
        self._button.grid_remove()
        if card.action is Action.NONE:
            if card.level is Level.OK:
                self._done.configure(image=style.icon(self, "circle-check-ok", 22))
                self._done.grid(row=0, column=2, rowspan=2, sticky="e")
            return
        self._button.configure(text=card.action.value)
        self._button.grid(row=0, column=2, rowspan=2, sticky="e")

    def _act(self) -> None:
        """Lanza la acción de la herramienta."""
        if self._card is not None:
            self._on_action(self._card)

    @property
    def button(self) -> ttk.Button:
        """Botón de acción (se desactiva mientras hay una operación)."""
        return self._button
