"""Ventana principal de atril.

Tres zonas: navegación a la izquierda, el apartado en el centro y la actividad
a la derecha (plegable), con cabecera arriba y barra de estado abajo. Toda la
lógica está en :mod:`atril.ops`; aquí solo se presenta y se pregunta. Las
operaciones van al :class:`~atril.gui.worker.Worker`: una cada vez, sin
congelar la ventana, y cada una queda como un evento de actividad.
"""

import contextlib
import sys
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from atril import __version__
from atril.checks import Finding, Level
from atril.config import ConfigError, load_station
from atril.config.station import STATION_FILE, Station, init_station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError, CancelledError
from atril.gui import style
from atril.gui.activity import ActivityLog, Event
from atril.gui.backups import BackupsView
from atril.gui.diagnostics import DiagnosticsView
from atril.gui.home import HomeView
from atril.gui.library import LibraryView
from atril.gui.model import status_word
from atril.gui.services import ServicesView
from atril.gui.settings import SettingsView
from atril.gui.syllabi import SyllabiView
from atril.gui.widgets import ACTIVITY_WIDTH, ActivityPanel, Header, Sidebar
from atril.gui.worker import Worker
from atril.ops import Reporter, service
from atril.ops.station import persist_station, saved_station

POLL_MS = 100
"""Cada cuánto se reparten los avisos del trabajo en segundo plano."""

STATUS_TTL = 60.0
"""Segundos que vale el estado de los servicios antes de volver a consultarlo."""

LIVE = frozenset({"Inicio", "Servicios"})
"""Apartados con servicios: se consultan de nuevo pasado :data:`STATUS_TTL`."""

NARROW = 1400
"""Anchura (a 100 %) por debajo de la que el panel de actividad se pliega solo."""

type View = (
    HomeView
    | SyllabiView
    | LibraryView
    | ServicesView
    | BackupsView
    | DiagnosticsView
    | SettingsView
)
"""Apartado de la ventana: un marco con ``refresh() -> bool``."""

SECTIONS = (
    ("Inicio", "house"),
    ("Temarios", "book-open"),
    ("Biblioteca", "library"),
    ("Servicios", "server"),
    ("Copias", "shield-check"),
    ("Diagnóstico", "stethoscope"),
    ("Ajustes", "settings"),
)
"""Apartados de la navegación, con su icono."""


class App(tk.Tk):
    """Ventana principal: navegación, apartados, actividad y barra de estado."""

    def __init__(self, station: Station) -> None:
        """Construye la ventana para ``station`` y muestra Inicio."""
        super().__init__(className="Atril")
        self.station = station
        self.worker = Worker(self)
        self.activity = ActivityLog(station.activity_file)
        self._event: Event | None = None
        self._actions: list[ttk.Button] = []
        self._cancels: list[ttk.Button] = []
        self._idle = True
        self._closing = False
        self._auto_collapsed = False
        self._loaded: dict[str, float] = {}
        self.closed = False
        self.title("Atril")
        style.apply(self)
        self.iconphoto(True, *(style.logo(self, size) for size in (256, 64, 32)))
        factor = style.scale(self)
        self.minsize(round(980 * factor), round(640 * factor))
        self.geometry(f"{round(1340 * factor)}x{round(820 * factor)}")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Configure>", self._on_resize, add="+")
        self.after(POLL_MS, self._poll)
        self.show_view("Inicio")

    # --- servicios para los apartados -----------------------------------------

    def run[T](
        self,
        text: str,
        task: Callable[[Reporter], T],
        on_done: Callable[[T], object],
        *,
        quiet: bool = False,
        title: str | None = None,
    ) -> bool:
        """Lanza ``task`` en segundo plano si no hay otra operación en marcha.

        Cada operación es un evento de actividad (``title`` o ``text``), salvo
        las lecturas ``quiet`` (al cambiar de apartado), que solo dejan rastro si
        fallan y no avisan si la ventana está ocupada.
        """
        if self._closing:
            return False
        name = title or text.rstrip(".… ")
        event = None if quiet else self.activity.start(name)

        def done(result: T) -> None:
            self._finish(event)
            on_done(result)

        def failed(exc: Exception) -> None:
            target = event or self.activity.start(name)
            self._finish(target, exc)
            self._show_error(exc)

        if not self.worker.submit(task, done, failed):
            if event is not None:
                self.activity.events.remove(event)
            if not quiet:
                self.log(Level.WARNING, "Espera a que termine la operación en curso.")
            return False
        self._event = event
        self._set_idle(False)
        self.on_busy(text)
        self._show_activity()
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
            self._status.configure(text="Cancelando: se para en cuanto sea seguro...")

    def log(self, level: Level, message: str) -> None:
        """Deja un aviso suelto en la actividad (sin operación detrás)."""
        event = self.activity.start(message)
        event.finish(level, "")
        self.activity.save(event)
        self._show_activity()

    def set_overall(self, level: Level) -> None:
        """Indicador general de la cabecera."""
        self._header.set_status(level, status_word(level))

    def show_view(self, name: str) -> None:
        """Muestra un apartado; solo vuelve a leer sus datos si han caducado.

        Cada apartado se lee la primera vez, tras cualquier operación (puede
        haber cambiado algo) y, en los de servicios, pasado :data:`STATUS_TTL`.
        Cambiar de apartado no espera a nada.
        """
        self._sidebar.select(name)
        view = self.views[name]
        for other in self.views.values():
            if other is not view:
                other.grid_remove()  # oculto no se recoloca al redimensionar
        view.grid()
        loaded = self._loaded.get(name)
        now = time.monotonic()
        if loaded is None or (name in LIVE and now - loaded > STATUS_TTL):
            if view.refresh():
                self._loaded[name] = now
        elif isinstance(view, HomeView | DiagnosticsView):
            view.shown()

    def check_now(self) -> None:
        """Vuelve a comprobar el estado (indicador de la cabecera) y va a Inicio."""
        self._loaded.pop("Inicio", None)
        self.show_view("Inicio")

    def close(self) -> None:
        """Cierra la ventana sin dejar operaciones a medias.

        Con una operación en marcha se le pide que pare en un punto seguro (o se
        espera a que termine si no admite cancelación) y la ventana se cierra
        después: nunca se corta el trabajo. Si DeepTutor sigue en marcha, se
        pregunta si pararlo.
        """
        if self._closing:
            return
        if self.worker.running:
            if messagebox.askyesno(
                "Atril",
                "Hay una operación en curso. Atril la parará en cuanto sea seguro "
                "(o esperará a que termine si no se puede parar) y se cerrará "
                "después. ¿Cerrar?",
                icon="warning",
                parent=self,
            ):
                self._closing = True
                self.worker.cancel.set()
                self._status.configure(text="Cerrando al terminar la operación...")
            return
        dt = DeepTutor(self.station)
        if dt.installed and dt.backend_up():
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
        """Navegación, cabecera, apartados, actividad y barra de estado."""
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._sidebar = Sidebar(self, self.show_view)
        self._sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self._header = Header(self, lambda: self.show_view("Ajustes"), self.check_now)
        self._header.grid(row=0, column=1, columnspan=2, sticky="ew")

        stack = tk.Frame(self, background=style.PAGE)
        stack.grid(row=1, column=1, sticky="nsew", padx=(24, 12), pady=20)
        stack.columnconfigure(0, weight=1)
        stack.rowconfigure(0, weight=1)
        builders = {
            "Inicio": HomeView,
            "Temarios": SyllabiView,
            "Biblioteca": LibraryView,
            "Servicios": ServicesView,
            "Copias": BackupsView,
            "Diagnóstico": DiagnosticsView,
            "Ajustes": SettingsView,
        }
        self.views: dict[str, View] = {}
        for name, icon in SECTIONS:
            self._sidebar.add(name, icon)
            view = builders[name](stack, self)
            view.grid(row=0, column=0, sticky="nsew")
            view.grid_remove()
            self.views[name] = view

        self._panel = ActivityPanel(self, lambda: self._show_history())
        width = round(ACTIVITY_WIDTH * style.scale(self))
        self._panel.configure(width=width)
        self._panel.grid(row=1, column=2, sticky="nsew", padx=(0, 24), pady=20)
        self._panel.grid_propagate(False)
        self._panel.show(self.activity.events)
        self._build_statusbar().grid(row=2, column=0, columnspan=3, sticky="ew")

    def _build_statusbar(self) -> tk.Frame:
        """Operación en curso a la izquierda y versión a la derecha."""
        bar = tk.Frame(self, background=style.SIDEBAR, padx=16, pady=6)
        bar.columnconfigure(1, weight=1)
        self._status = style.label(
            bar, "Listo", background=style.SIDEBAR, font=style.SMALL
        )
        self._status.grid(row=0, column=0, sticky="w")
        self._bar = ttk.Progressbar(bar, length=180, mode="indeterminate")
        self._bar.grid(row=0, column=1, sticky="w", padx=12)
        self._bar.grid_remove()
        style.label(
            bar,
            f"atril {__version__}",
            background=style.SIDEBAR,
            font=style.SMALL,
            color=style.MUTED,
        ).grid(row=0, column=2, sticky="e")
        return bar

    def _on_resize(self, event: tk.Event) -> None:
        """Pliega la actividad en ventanas estrechas y la recupera al ensanchar."""
        if event.widget is not self:
            return
        narrow = event.width < NARROW * style.scale(self)
        if narrow and self._panel.expanded:
            self._panel.toggle()
            self._auto_collapsed = True
        elif not narrow and self._auto_collapsed and not self._panel.expanded:
            self._panel.toggle()
            self._auto_collapsed = False

    # --- avisos del trabajo en segundo plano ------------------------------------

    def _poll(self) -> None:
        """Reparte los avisos del trabajo y vuelve a programarse."""
        self.worker.poll()
        if self._closing and not self.worker.running:
            self._quit(None)
            return
        if not self.worker.running and not self._idle:
            self._set_idle(True)
            self.on_busy(None)
        self.after(POLL_MS, self._poll)

    def on_show(self, title: str | None, findings: list[Finding]) -> None:
        """Las comprobaciones van al detalle de la operación en curso."""
        if self._event is not None:
            self._event.add(findings)

    def on_busy(self, text: str | None) -> None:
        """Muestra la espera en la barra de estado."""
        if text is None:
            self._status.configure(text="Listo")
            self._bar.stop()
            self._bar.grid_remove()
            return
        self._status.configure(text=text)
        if str(self._bar.cget("mode")) != "indeterminate" or not (
            self._bar.winfo_ismapped()
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

    def _finish(self, event: Event | None, exc: Exception | None = None) -> None:
        """Cierra el evento de la operación y lo guarda."""
        if self._event is event:
            self._event = None
        if event is None:
            return
        if isinstance(exc, CancelledError):
            event.finish(Level.WARNING, _sentence(str(exc)))
        elif exc is not None:
            text = str(exc) if isinstance(exc, AtrilError) else repr(exc)
            event.add([Finding(Level.ERROR, text)])
            if isinstance(exc, AtrilError):
                event.detail.extend((Level.INFO.value, line) for line in exc.log)
            event.finish(Level.ERROR, _sentence(text))
        else:
            event.finish()
        self._loaded.clear()  # la operación puede haber cambiado cualquier dato
        self.activity.save(event)
        self._show_activity()

    def _show_activity(self) -> None:
        """Repinta el panel de actividad."""
        self._panel.show(self.activity.events)

    def _show_history(self) -> None:
        """«Ver todo»: el historial completo, en Diagnóstico."""
        self.show_view("Diagnóstico")
        view = self.views["Diagnóstico"]
        if isinstance(view, DiagnosticsView):
            view.show_history()

    def _show_error(self, exc: Exception) -> None:
        """Muestra un error en un diálogo (las cancelaciones, solo en la actividad)."""
        if isinstance(exc, CancelledError) or self._closing:
            return
        message = _sentence(str(exc) if isinstance(exc, AtrilError) else repr(exc))
        detail = ""
        if isinstance(exc, AtrilError) and exc.log:
            detail = "\n\nEl detalle técnico está en Diagnóstico > Historial."
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
        self.closed = True
        self.destroy()


def _sentence(text: str) -> str:
    """Primera letra en mayúscula."""
    return text[:1].upper() + text[1:]


def _stopper(station: Station) -> Callable[[Reporter], None]:
    """Trabajo que para DeepTutor."""

    def stop(reporter: Reporter) -> None:
        service.stop(service.installed(station), reporter)

    return stop


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
    style.register_fonts()
    station = choose_station()
    if station is None:
        return
    App(station).mainloop()
