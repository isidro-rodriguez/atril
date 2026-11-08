"""Ventana principal de atril.

Barra lateral con los apartados (Inicio, Temarios), cabecera, el apartado activo,
la actividad reciente y la barra de estado. Toda la lógica está en
:mod:`atril.ops`; aquí solo se presenta y se pregunta. Las operaciones van al
:class:`~atril.gui.worker.Worker`: una cada vez, sin congelar la ventana.
"""

import contextlib
import sys
import time
import tkinter as tk
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from atril import __version__
from atril.checks import Finding, Level
from atril.config import ConfigError, load_station
from atril.config.station import STATION_FILE, Station, init_station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError, CancelledError
from atril.gui import style
from atril.gui.home import HomeView
from atril.gui.syllabi import SyllabiView
from atril.gui.worker import Worker
from atril.ops import Reporter, service
from atril.ops.station import persist_station, saved_station

POLL_MS = 100
"""Cada cuánto se reparten los avisos del trabajo en segundo plano."""

TAGLINE = "Aprende. Practica. Avanza."
"""Lema de la cabecera."""

type View = HomeView | SyllabiView
"""Apartado de la ventana: un marco con ``refresh()``."""


class App(tk.Tk):
    """Ventana principal: navegación, apartados, actividad y barra de estado."""

    def __init__(self, station: Station) -> None:
        """Construye la ventana para ``station`` y lanza la primera comprobación."""
        super().__init__(className="Atril")
        self.station = station
        self.worker = Worker(self)
        self._actions: list[ttk.Button] = []
        self._cancels: list[ttk.Button] = []
        self._idle = True
        self._images = _load_icons(self)
        self.title("Atril")
        self.iconphoto(True, *self._images.values())
        self.minsize(980, 640)
        self.geometry("1180x780")
        style.apply(self)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(POLL_MS, self._poll)
        self.show_view("Inicio")

    # --- servicios para los apartados -----------------------------------------

    def run[T](
        self,
        text: str,
        task: Callable[[Reporter], T],
        on_done: Callable[[T], None],
        *,
        quiet: bool = False,
    ) -> bool:
        """Lanza ``task`` en segundo plano si no hay otra operación en marcha.

        Con ``quiet`` (lecturas al cambiar de apartado) no avisa si está ocupado.
        """
        if not self.worker.submit(task, on_done, self._show_error):
            if not quiet:
                self.log(Level.WARNING, "Espera a que termine la operación en curso.")
            return False
        self._set_idle(False)
        self.on_busy(text)
        return True

    def action(self, button: ttk.Button) -> ttk.Button:
        """Registra un botón que se desactiva mientras hay una operación."""
        self._actions.append(button)
        return button

    def cancel_button(self, button: ttk.Button) -> ttk.Button:
        """Registra un botón que solo se activa mientras hay una operación."""
        self._cancels.append(button)
        button.state(["disabled"])
        return button

    def cancel(self) -> None:
        """Pide a la operación en curso que pare en un punto seguro."""
        if self.worker.running:
            self.worker.cancel.set()
            self.log(Level.INFO, "Cancelando: se para en cuanto sea seguro...")

    def log(self, level: Level, message: str) -> None:
        """Añade una línea a la actividad."""
        self._log.configure(state="normal")
        self._log.insert("end", time.strftime("%H:%M:%S  "), "time")
        line = f"{style.LEVEL_SYMBOLS[level]} {message}\n"
        self._log.insert("end", line, level.value)
        self._log.see("end")
        self._log.configure(state="disabled")

    def show_view(self, name: str) -> None:
        """Muestra un apartado y lo actualiza."""
        for key, (item, view) in self._views.items():
            selected = key == name
            item.configure(background=style.SELECTED if selected else style.SIDEBAR)
            if selected:
                view.tkraise()
        self._views[name][1].refresh()

    def close(self) -> None:
        """Cierra la ventana; si DeepTutor está en marcha, pregunta si pararlo."""
        if self.worker.running and not messagebox.askyesno(
            "Atril",
            "Hay una operación en curso. Si sales ahora quedará a medias. ¿Salir?",
            icon="warning",
            parent=self,
        ):
            return
        dt = DeepTutor(self.station)
        if not self.worker.running and dt.installed and dt.backend_up():
            answer = messagebox.askyesnocancel(
                "Atril",
                "DeepTutor sigue en marcha. ¿Pararlo antes de salir?\n\n"
                "Si no lo paras, podrás seguir usándolo en el navegador.",
                parent=self,
            )
            if answer is None:
                return
            if answer:
                self.run("Deteniendo DeepTutor...", _stopper(self.station), self._quit)
                return
        self._quit(None)

    # --- construcción -----------------------------------------------------------

    def _build(self) -> None:
        """Barra lateral a la izquierda; cabecera, apartado y actividad a la derecha."""
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        content = tk.Frame(self, background=style.PAGE)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        self._build_banner(content).grid(row=0, column=0, sticky="ew")

        stack = tk.Frame(content, background=style.PAGE)
        stack.grid(row=1, column=0, sticky="nsew", padx=20, pady=(16, 12))
        stack.columnconfigure(0, weight=1)
        stack.rowconfigure(0, weight=1)
        views: list[tuple[str, str, View]] = [
            ("Inicio", "⌂", HomeView(stack, self)),
            ("Temarios", "☰", SyllabiView(stack, self)),
        ]
        for _, _, view in views:
            view.grid(row=0, column=0, sticky="nsew")

        self._build_activity(content).grid(
            row=2, column=0, sticky="ew", padx=20, pady=(0, 16)
        )
        self._views = self._build_sidebar(views)
        self.views = {name: view for name, _, view in views}
        self._build_statusbar().grid(row=1, column=0, columnspan=2, sticky="ew")

    def _build_sidebar(
        self, views: list[tuple[str, str, View]]
    ) -> dict[str, tuple[tk.Label, View]]:
        """Apartados de la aplicación; devuelve cada uno con su entrada."""
        bar = tk.Frame(self, background=style.SIDEBAR, width=220, padx=10, pady=16)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.columnconfigure(0, weight=1)
        entries = {}
        for row, (name, icon, view) in enumerate(views):
            item = style.label(
                bar,
                f"{icon}   {name}",
                background=style.SIDEBAR,
                font=style.STRONG,
                color=style.NAVY,
                padx=14,
                pady=8,
            )
            item.configure(cursor="hand2")
            item.grid(row=row, column=0, sticky="ew", pady=2)
            item.bind("<Button-1>", lambda _, n=name: self.show_view(n))
            entries[name] = (item, view)
        bar.rowconfigure(len(views), weight=1)
        style.label(
            bar,
            f"atril {__version__}",
            background=style.SIDEBAR,
            font=style.CAPTION,
            color=style.MUTED,
            padx=8,
        ).grid(row=len(views) + 1, column=0, sticky="w")
        return entries

    def _build_banner(self, parent: tk.Misc) -> tk.Frame:
        """Cabecera con el icono, el nombre y el lema."""
        banner = tk.Frame(parent, background=style.BANNER, padx=24, pady=14)
        tk.Label(banner, image=self._images[64], background=style.BANNER).grid(
            row=0, column=0, rowspan=2, padx=(0, 16)
        )
        style.label(
            banner, "Atril", background=style.BANNER, font=style.TITLE, color=style.NAVY
        ).grid(row=0, column=1, sticky="sw")
        style.label(
            banner,
            TAGLINE,
            background=style.BANNER,
            font=style.SUBTITLE,
            color=style.BLUE,
        ).grid(row=1, column=1, sticky="nw")
        return banner

    def _build_activity(self, parent: tk.Misc) -> tk.Frame:
        """Registro de lo que va haciendo atril, común a todos los apartados."""
        frame = style.card(parent, "Actividad")
        frame.columnconfigure(0, weight=1)
        self._log = tk.Text(
            frame,
            height=6,
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=style.BODY,
            background=style.CARD,
            foreground=style.TEXT,
            state="disabled",
        )
        self._log.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self._log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scroll.set)
        for level, color in style.LEVEL_COLORS.items():
            self._log.tag_configure(level.value, foreground=color)
        self._log.tag_configure("time", foreground=style.MUTED)
        return frame

    def _build_statusbar(self) -> tk.Frame:
        """Estado del trabajo en curso y ruta de la estación."""
        bar = tk.Frame(self, background=style.SIDEBAR, padx=12, pady=4)
        bar.columnconfigure(1, weight=1)
        self._status = style.label(
            bar, "Listo", background=style.SIDEBAR, font=style.CAPTION
        )
        self._status.grid(row=0, column=0, sticky="w")
        self._bar = ttk.Progressbar(bar, length=180, mode="indeterminate")
        self._bar.grid(row=0, column=1, sticky="e", padx=12)
        self._bar.grid_remove()
        style.label(
            bar,
            str(self.station.root),
            background=style.SIDEBAR,
            font=style.CAPTION,
            color=style.MUTED,
        ).grid(row=0, column=2, sticky="e")
        return bar

    # --- avisos del trabajo en segundo plano ------------------------------------

    def _poll(self) -> None:
        """Reparte los avisos del trabajo y vuelve a programarse."""
        self.worker.poll()
        if not self.worker.running and not self._idle:
            self._set_idle(True)
            self.on_busy(None)
        self.after(POLL_MS, self._poll)

    def on_show(self, title: str | None, findings: list[Finding]) -> None:
        """Escribe las comprobaciones en la actividad."""
        for finding in findings:
            self.log(finding.level, finding.message)

    def on_busy(self, text: str | None) -> None:
        """Muestra la espera en la barra de estado."""
        if text is None:
            self._status.configure(text="Listo")
            self._bar.stop()
            self._bar.grid_remove()
            return
        self._status.configure(text=text)
        if (
            str(self._bar.cget("mode")) != "indeterminate"
            or not self._bar.winfo_ismapped()
        ):
            self._bar.configure(mode="indeterminate")
            self._bar.grid()
            self._bar.start(15)

    def on_progress(self, text: str | None, total: int) -> None:
        """Barra de avance de un trabajo medible."""
        if text is None:
            self.on_busy(None)
            return
        self._status.configure(text=text)
        self._bar.stop()
        self._bar.configure(mode="determinate", maximum=max(total, 1), value=0)
        self._bar.grid()

    def on_advance(self, amount: int) -> None:
        """Avanza la barra."""
        self._bar.step(amount)

    # --- auxiliares ---------------------------------------------------------------

    def _show_error(self, exc: Exception) -> None:
        """Muestra un error en la actividad y, salvo cancelaciones, en un diálogo."""
        message = str(exc) if isinstance(exc, AtrilError) else repr(exc)
        message = message[:1].upper() + message[1:]
        if isinstance(exc, CancelledError):
            self.log(Level.WARNING, message)
            return
        self.log(Level.ERROR, message)
        detail = ""
        if isinstance(exc, AtrilError) and exc.log:
            detail = f"\n\nÚltimas líneas de {exc.log_title}:\n" + "\n".join(
                exc.log[-10:]
            )
            for line in exc.log:
                self.log(Level.INFO, line)
        messagebox.showerror("Atril", message + detail, parent=self)

    def _set_idle(self, idle: bool) -> None:
        """Activa los botones de acción o los de cancelar según haya operación."""
        self._idle = idle
        for button in self._actions:
            button.state(["!disabled"] if idle else ["disabled"])
        for button in self._cancels:
            button.state(["disabled"] if idle else ["!disabled"])

    def _quit(self, _: object) -> None:
        """Cierra la aplicación."""
        self.destroy()


def _stopper(station: Station) -> Callable[[Reporter], None]:
    """Trabajo que para DeepTutor."""

    def stop(reporter: Reporter) -> None:
        service.stop(service.installed(station), reporter)

    return stop


def _load_icons(root: tk.Tk) -> dict[int, tk.PhotoImage]:
    """Icono de atril en 256, 64 y 32 px (del paquete)."""
    folder = resources.files("atril.gui") / "recursos"
    return {
        size: tk.PhotoImage(
            master=root, data=(folder / f"icono-{size}.png").read_bytes()
        )
        for size in (256, 64, 32)
    }


# --- arranque ----------------------------------------------------------------------


def choose_station() -> Station | None:
    """Estación guardada o, en la primera ejecución, la que elija el usuario."""
    root = saved_station()
    problem = None
    if root is not None and (root / STATION_FILE).is_file():
        try:
            return load_station(root)
        except ConfigError as exc:
            problem = exc
    picker = tk.Tk()
    picker.withdraw()
    style.apply(picker)
    try:
        if problem is not None:
            _config_error(problem, picker)
            return None
        return _first_run(picker)
    finally:
        picker.destroy()


def _first_run(parent: tk.Tk) -> Station | None:
    """Pregunta por la carpeta de la estación y, si está vacía, la inicializa."""
    messagebox.showinfo(
        "Atril: primera ejecución",
        "Elige la carpeta de tu estación de estudio. Si ya tienes una, selecciona la "
        f"carpeta que contiene {STATION_FILE}; si no, elige o crea una carpeta vacía "
        "y atril la preparará.",
        parent=parent,
    )
    while True:
        answer = filedialog.askdirectory(
            title="Carpeta de la estación", mustexist=False, parent=parent
        )
        if not answer:
            return None
        root = Path(answer).resolve()
        if not (root / STATION_FILE).is_file():
            if not messagebox.askyesno(
                "Atril",
                f"No hay {STATION_FILE} en {root}.\n\n¿Crear ahí una estación nueva?",
                parent=parent,
            ):
                continue
            try:
                init_station(root)
            except (ConfigError, OSError) as exc:
                messagebox.showerror("Atril", str(exc), parent=parent)
                continue
        try:
            station = load_station(root)
        except ConfigError as exc:
            _config_error(exc, parent)
            continue
        persist_station(root)
        return station


def _config_error(exc: ConfigError, parent: tk.Misc) -> None:
    """Explica un ``atril.toml`` no válido."""
    messagebox.showerror(
        "Atril", f"{exc}\n\nCorrígelo y vuelve a abrir atril.", parent=parent
    )


def _prepare_windows() -> None:
    """Texto nítido en pantallas escaladas e icono propio en la barra de tareas."""
    if sys.platform != "win32":
        return
    import ctypes

    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("atril.gui")


def run() -> None:
    """Abre la ventana principal (tras la primera ejecución, si hace falta)."""
    _prepare_windows()
    station = choose_station()
    if station is None:
        return
    App(station).mainloop()
