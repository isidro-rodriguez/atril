"""Componentes de la ventana: navegación, cabecera, panel de actividad y accesos.

Pocos y concretos: cada uno se usa en varios sitios o aísla una parte de la
ventana. La lógica de presentación sin Tk está en :mod:`atril.gui.model` y
:mod:`atril.gui.activity`.
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from atril.checks import Level
from atril.gui import style
from atril.gui.activity import Event, when_label

SIDEBAR_WIDTH = 230
ACTIVITY_WIDTH = 320
"""Anchuras a 100 % (se escalan con la pantalla)."""


class Sidebar(tk.Frame):
    """Navegación lateral: logotipo arriba y un apartado por fila."""

    def __init__(self, parent: tk.Misc, on_select: Callable[[str], None]) -> None:
        """Construye el logotipo; los apartados se añaden con :meth:`add`."""
        width = round(SIDEBAR_WIDTH * style.scale(parent))
        super().__init__(parent, background=style.SIDEBAR, width=width)
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        self._on_select = on_select
        self._items: dict[str, tuple[tk.Frame, tk.Label, str]] = {}
        tk.Label(self, image=style.logo(self, 96), background=style.SIDEBAR).grid(
            row=0, column=0, pady=(22, 26)
        )

    def add(self, name: str, icon: str) -> None:
        """Añade un apartado con su icono de Lucide (sin variante)."""
        row = len(self._items) + 1
        item = tk.Frame(self, background=style.SIDEBAR, cursor="hand2")
        item.grid(row=row, column=0, sticky="ew", padx=12, pady=2)
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
            pady=9,
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


class Header(tk.Frame):
    """Nombre, lema e indicador general de estado."""

    def __init__(
        self,
        parent: tk.Misc,
        on_settings: Callable[[], None],
        on_check: Callable[[], None],
    ) -> None:
        """Construye la cabecera; el estado se pone con :meth:`set_status`.

        Pulsar el indicador vuelve a comprobar el estado.
        """
        super().__init__(parent, background=style.HEADER, padx=28, pady=18)
        self.columnconfigure(0, weight=1)
        style.label(self, "Atril", background=style.HEADER, font=style.DISPLAY).grid(
            row=0, column=0, sticky="w"
        )
        style.label(
            self,
            "Aprende. Practica. Avanza.",
            background=style.HEADER,
            font=style.SUBTITLE,
            color=style.MUTED,
        ).grid(row=1, column=0, sticky="w")
        self._pill = style.label(
            self,
            "  Comprobando…",
            background=style.CARD,
            font=style.STRONG,
            padx=14,
            pady=6,
        )
        self._pill.grid(row=0, column=1, rowspan=2, padx=(0, 14))
        self._pill.configure(cursor="hand2")
        self._pill.bind("<Button-1>", lambda _: on_check())
        settings = tk.Label(
            self,
            image=style.icon(self, "settings-nav"),
            background=style.HEADER,
            cursor="hand2",
        )
        settings.grid(row=0, column=2, rowspan=2)
        settings.bind("<Button-1>", lambda _: on_settings())

    def set_status(self, level: Level, text: str) -> None:
        """Indicador general: icono de nivel y una palabra."""
        self._pill.configure(
            text=f"  {text}",
            image=style.icon(self, style.LEVEL_ICONS[level], 18),
            compound="left",
            foreground=style.LEVEL_COLORS[level]
            if level is not Level.OK
            else style.TEXT,
        )


class ActivityPanel(tk.Frame):
    """Panel derecho con las últimas operaciones; se puede plegar."""

    SHOWN = 30
    """Eventos visibles en el panel (el resto, en «Ver todo»)."""

    def __init__(self, parent: tk.Misc, on_show_all: Callable[[], None]) -> None:
        """Construye la tarjeta con su cabecera y la lista desplazable."""
        super().__init__(parent, background=style.PAGE)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.expanded = True
        self._card = style.card(self)
        self._card.grid(row=0, column=0, sticky="nsew")
        self._card.columnconfigure(0, weight=1)
        self._card.rowconfigure(1, weight=1)
        head = tk.Frame(self._card, background=style.CARD)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        head.columnconfigure(0, weight=1)
        style.label(head, "Actividad", font=style.SUBTITLE).grid(
            row=0, column=0, sticky="w"
        )
        more = style.label(head, "Ver todo", color=style.ACCENT, font=style.STRONG)
        more.configure(cursor="hand2")
        more.grid(row=0, column=1, padx=(0, 10))
        more.bind("<Button-1>", lambda _: on_show_all())
        self._toggle = tk.Label(
            head,
            image=style.icon(self, "panel-right-close-nav", 18),
            background=style.CARD,
            cursor="hand2",
        )
        self._toggle.grid(row=0, column=2)
        self._toggle.bind("<Button-1>", lambda _: self.toggle())
        self._list = tk.Frame(self._card, background=style.CARD)
        self._list.grid(row=1, column=0, sticky="nsew")
        self._list.columnconfigure(1, weight=1)
        self._collapsed = tk.Label(
            self,
            image=style.icon(self, "panel-right-open-nav", 18),
            background=style.PAGE,
            cursor="hand2",
        )
        self._collapsed.bind("<Button-1>", lambda _: self.toggle())
        self._wrap = round((ACTIVITY_WIDTH - 110) * style.scale(self))

    def toggle(self) -> None:
        """Pliega o despliega el panel (los eventos se conservan)."""
        self.expanded = not self.expanded
        full = round(ACTIVITY_WIDTH * style.scale(self))
        self.configure(width=full if self.expanded else round(full / 8))
        if self.expanded:
            self._collapsed.grid_remove()
            self._card.grid()
        else:
            self._card.grid_remove()
            self._collapsed.grid(row=0, column=0, sticky="n", pady=8)

    def show(self, events: list[Event]) -> None:
        """Pinta los últimos eventos, el más reciente arriba."""
        for widget in self._list.winfo_children():
            widget.destroy()
        if not events:
            style.label(self._list, "Sin actividad todavía.", color=style.MUTED).grid(
                row=0, column=0, columnspan=3, sticky="w"
            )
        for row, event in enumerate(events[: self.SHOWN]):
            name = (
                "loader-circle-info"
                if event.running
                else (style.LEVEL_ICONS[event.level])
            )
            tk.Label(
                self._list, image=style.icon(self, name, 18), background=style.CARD
            ).grid(
                row=row * 2, column=0, rowspan=2, sticky="n", padx=(0, 10), pady=(2, 0)
            )
            style.label(self._list, event.title, font=style.STRONG).grid(
                row=row * 2, column=1, sticky="w"
            )
            style.label(
                self._list,
                "ahora" if event.running else when_label(event.when),
                font=style.SMALL,
                color=style.MUTED,
            ).grid(row=row * 2, column=2, sticky="ne", padx=(8, 0))
            style.label(
                self._list,
                event.summary,
                font=style.SMALL,
                color=style.MUTED,
                wraplength=self._wrap,
            ).grid(row=row * 2 + 1, column=1, columnspan=2, sticky="w", pady=(0, 12))


class QuickTile(tk.Frame):
    """Acceso rápido: icono grande, título y subtítulo; todo él es clicable."""

    def __init__(
        self,
        parent: tk.Misc,
        icon: str,
        title: str,
        subtitle: str,
        command: Callable[[], None],
    ) -> None:
        """Construye la baldosa con borde fino."""
        super().__init__(
            parent,
            background=style.CARD,
            highlightthickness=1,
            highlightbackground=style.BORDER,
            cursor="hand2",
            padx=10,
            pady=12,
        )
        self.columnconfigure(0, weight=1)
        widgets = [
            tk.Label(self, image=style.icon(self, icon, 22), background=style.CARD),
            style.label(self, title, font=style.STRONG),
            style.label(self, subtitle, font=style.SMALL, color=style.MUTED),
        ]
        for row, widget in enumerate(widgets):
            widget.configure(anchor="center")
            widget.grid(row=row, column=0, pady=(0, 4) if row == 0 else 0)
        self._enabled = True
        for widget in (self, *widgets):
            widget.bind("<Button-1>", lambda _: self._enabled and command())
            widget.bind("<Enter>", lambda _: self._hover(True))
            widget.bind("<Leave>", lambda _: self._hover(False))

    def _hover(self, inside: bool) -> None:
        """Borde azul al pasar por encima."""
        self.configure(highlightbackground=style.ACCENT if inside else style.BORDER)

    def state(self, states: list[str]) -> None:
        """Compatible con ``ttk``: ``["disabled"]`` o ``["!disabled"]``."""
        self._enabled = "disabled" not in states


def separator(parent: tk.Misc) -> ttk.Separator:
    """Separador horizontal fino."""
    return ttk.Separator(parent, orient="horizontal")
