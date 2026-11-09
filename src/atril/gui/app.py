"""Ventana principal de atril.

Ventana fija de 1024 x 700 (a 100 %): navegación a la izquierda, el apartado a
la derecha y el pie con el estado de los servicios y la operación en curso. Toda
la lógica está en :mod:`atril.ops`; aquí solo se presenta y se pregunta. Las
operaciones van al :class:`~atril.gui.worker.Worker`: una cada vez, sin congelar
la ventana, y cada una queda como un evento de actividad.
"""

import contextlib
import json
import sys
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from atril import __version__
from atril.checks import Finding, Level
from atril.config import ConfigError, load_station
from atril.config.station import STATION_FILE, Station, init_station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError, CancelledError
from atril.gui import style, tray
from atril.gui.activity import ActivityLog, Event
from atril.gui.backups import BackupsView
from atril.gui.dialogs import ask_three, ask_yes_no, show_message
from atril.gui.history import HistoryView
from atril.gui.home import HomeView
from atril.gui.library import LibraryView
from atril.gui.model import (
    CloseAction,
    Facts,
    TrayCommand,
    close_action,
    service_states,
    tray_menu,
    tray_tooltip,
)
from atril.gui.settings import SettingsView
from atril.gui.syllabi import SyllabiView
from atril.gui.widgets import Footer, Sidebar
from atril.gui.worker import Worker
from atril.ops import Reporter, service, updates
from atril.ops.station import persist_station, saved_station

POLL_MS = 100
"""Cada cuánto se reparten los avisos del trabajo en segundo plano."""

WIDTH, HEIGHT = 1024, 700
"""Tamaño fijo de la ventana a 100 % (se escala con la pantalla)."""

UPDATE_DELAY_MS = 1500
"""Espera tras abrir antes de buscar una versión nueva (no retrasa el arranque)."""

STATUS_TTL = 60.0
"""Segundos que vale el estado de los servicios antes de volver a consultarlo."""

type View = (
    HomeView | SyllabiView | LibraryView | BackupsView | HistoryView | SettingsView
)
"""Apartado de la ventana: un marco con ``refresh() -> bool``."""

SECTIONS = (
    ("Inicio", "house", HomeView),
    ("Temarios", "book-open", SyllabiView),
    ("Biblioteca", "library", LibraryView),
    ("Backups", "shield-check", BackupsView),
    ("Actividad", "activity", HistoryView),
    ("Ajustes", "settings", SettingsView),
)
"""Apartados de la navegación, con su icono y su clase."""

ALWAYS = frozenset({"Actividad"})
"""Apartados que se repintan cada vez (leen datos ya en memoria)."""


class App(tk.Tk):
    """Ventana principal: navegación, apartados y pie de ventana."""

    def __init__(self, station: Station) -> None:
        """Construye la ventana para ``station`` y muestra Inicio."""
        super().__init__(className="Atril")
        self.station = station
        self.worker = Worker(self)
        self.activity = ActivityLog(station.activity_file)
        self._event: Event | None = None
        self._quiet = False
        self._actions: list[ttk.Button] = []
        self._cancels: list[ttk.Button] = []
        self._idle = True
        self._closing = False
        self._loaded: dict[str, float] = {}
        self._status_at = 0.0
        self.syllabus_id: str | None = self._remembered_syllabus()
        self.closed = False
        self.hidden = False
        """La ventana está oculta en el área de notificación."""
        self._stop_on_quit = False
        self._deeptutor_up = False
        self._expected_change = False
        self._hinted = False
        self._warned = False
        self.title("Atril")
        _fit_scale(self)
        style.apply(self)
        self.iconphoto(True, *(style.logo(self, size) for size in (256, 64, 32)))
        factor = style.scale(self)
        self.geometry(f"{round(WIDTH * factor)}x{round(HEIGHT * factor)}")
        self.resizable(False, False)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.tray = tray.create()
        """Icono del área de notificación (``None`` fuera de Windows)."""
        self.after(POLL_MS, self._poll)
        self.show_view("Inicio")
        if station.atril.check_updates:
            self.after(UPDATE_DELAY_MS, self._check_updates)

    # --- servicios para los apartados -----------------------------------------

    def run[T](
        self,
        text: str,
        task: Callable[[Reporter], T],
        on_done: Callable[[T], object],
        *,
        quiet: bool = False,
        title: str | None = None,
        on_error: Callable[[Exception], object] | None = None,
    ) -> bool:
        """Lanza ``task`` en segundo plano si no hay otra operación en marcha.

        Cada operación es un evento de actividad (``title`` o ``text``). Las
        lecturas ``quiet`` (al mostrar un apartado) no dejan rastro ni bloquean
        botones; si fallan, se llama a ``on_error`` (o no se hace nada). Una
        operación pedida mientras corre una lectura espera a que acabe.
        """
        if self._closing:
            return False
        if self.worker.running:
            if self._quiet and not quiet:
                self.after(
                    POLL_MS,
                    lambda: self.run(
                        text, task, on_done, title=title, on_error=on_error
                    ),
                )
                return True
            if not quiet:
                show_message(
                    self,
                    "Operación en curso",
                    "Espera a que termine la operación en curso.",
                )
            return False
        name = title or text.rstrip(".… ")
        event = None if quiet else self.activity.start(name)

        def done(result: T) -> None:
            self._finish(event)
            on_done(result)

        def failed(exc: Exception) -> None:
            if quiet:
                self._finish(None)
                if on_error is not None:
                    on_error(exc)
                return
            self._finish(event, exc)
            if on_error is not None:
                on_error(exc)
            self._show_error(exc)

        self.worker.submit(task, done, failed)
        self._event = event
        self._quiet = quiet
        if not quiet:
            self._set_idle(False)
            self.on_busy(text)
            self._activity_changed()
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
        if self.worker.running and not self._quiet:
            self.worker.cancel.set()
            self._footer.status.configure(
                text="Cancelando: se para en cuanto sea seguro..."
            )

    def log(self, level: Level, message: str) -> None:
        """Deja un aviso suelto en la actividad (sin operación detrás)."""
        event = self.activity.start(message)
        event.finish(level, "")
        self._save(event)
        self._activity_changed()

    def set_facts(self, facts: Facts) -> None:
        """Estado de los servicios en el pie de ventana.

        Con la ventana oculta, avisa si DeepTutor se para sin una operación de
        atril detrás.
        """
        self._status_at = time.monotonic()
        for name, (level, text) in service_states(facts).items():
            self._footer.set_service(name, level, text)
        was_up, self._deeptutor_up = self._deeptutor_up, facts.backend_up
        stopped = was_up and not facts.backend_up and not self._expected_change
        if self.hidden and stopped and self.tray is not None:
            self.tray.notify(
                "DeepTutor se ha detenido",
                "Atril sigue en el área de notificación.",
                Level.WARNING,
            )
        self._expected_change = False

    def choose_syllabus(self, syllabus_id: str | None) -> None:
        """Temario activo (compartido por Temarios y Biblioteca) y lo recuerda."""
        if syllabus_id == self.syllabus_id:
            return
        self.syllabus_id = syllabus_id
        path = self.station.window_state_file
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"temario": syllabus_id}), encoding="utf-8")

    def show_view(self, name: str) -> None:
        """Muestra un apartado; solo vuelve a leer sus datos si han caducado.

        Cada apartado se lee la primera vez y tras cualquier operación (puede
        haber cambiado algo); Inicio, además, pasado :data:`STATUS_TTL`.
        Cambiar de apartado no espera a nada.
        """
        self._sidebar.select(name)
        view = self.views[name]
        for other in self.views.values():
            if other is not view:
                other.grid_remove()  # oculto no se recoloca ni se repinta
        view.grid()
        loaded = self._loaded.get(name)
        now = time.monotonic()
        stale = name == "Inicio" and now - (loaded or 0) > STATUS_TTL
        if loaded is None or stale or name in ALWAYS:
            if view.refresh():
                self._loaded[name] = now
        elif isinstance(view, SyllabiView | LibraryView):
            view.follow_syllabus()

    def close(self) -> None:
        """Cierra la ventana sin dejar operaciones a medias.

        Con DeepTutor en marcha, la ventana se oculta en el área de notificación
        (la operación en curso, si la hay, sigue). Si no, con una operación en
        marcha se le pide que pare en un punto seguro (o se espera a que termine
        si no admite cancelación) y la ventana se cierra después: nunca se corta
        el trabajo. Sin área de notificación, si DeepTutor sigue en marcha, se
        pregunta si pararlo.
        """
        if self._closing:
            return
        dt = DeepTutor(self.station)
        action = close_action(
            tray=self.tray is not None,
            deeptutor_up=dt.installed and dt.backend_up(),
            busy=self.worker.running and not self._quiet,
        )
        if action is CloseAction.HIDE:
            self.hide_window()
            return
        if action is CloseAction.WAIT:
            if ask_yes_no(
                self,
                "Cerrar atril",
                "Hay una operación en curso. Atril la parará en cuanto sea seguro "
                "(o esperará a que termine si no se puede parar) y se cerrará "
                "después.",
                "Cerrar",
                level=Level.WARNING,
            ):
                self._closing = True
                self.worker.cancel.set()
                self._footer.status.configure(
                    text="Cerrando al terminar la operación..."
                )
            return
        if action is CloseAction.ASK_STOP:
            answer = ask_three(
                self,
                "Cerrar atril",
                "DeepTutor sigue en marcha. ¿Pararlo antes de salir? Si no lo "
                "paras, podrás seguir usándolo en el navegador.",
                "Parar y salir",
                "Salir sin parar",
            )
            if answer is None:
                return
            if answer:
                self.run("Deteniendo DeepTutor...", _stopper(self.station), self._quit)
                return
        self._quit(None)

    def hide_window(self) -> None:
        """Oculta la ventana y deja el icono en el área de notificación."""
        if self.tray is None:
            return
        self.withdraw()
        self.hidden = True
        self._update_tray()
        self.tray.show_icon()
        if not self._hinted:
            self._hinted = True
            self.tray.notify(
                "Atril sigue abierto",
                "DeepTutor sigue en marcha. Pulsa el icono para volver a la ventana.",
            )

    def show_window(self) -> None:
        """Vuelve a mostrar la ventana y quita el icono."""
        if self.tray is not None:
            self.tray.hide_icon()
        self.hidden = False
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_all(self) -> None:
        """Sale de atril y para DeepTutor y el Ollama que abrió atril.

        Con una operación en marcha, se muestra la ventana y se pregunta: se le
        pide que pare en un punto seguro y se sale después.
        """
        if self._closing:
            return
        if self.worker.running and not self._quiet:
            self.show_window()
            if ask_yes_no(
                self,
                "Salir de atril",
                "Hay una operación en curso. Atril la parará en cuanto sea seguro "
                "(o esperará a que termine si no se puede parar). Después parará "
                "DeepTutor y Ollama y se cerrará.",
                "Salir",
                level=Level.WARNING,
            ):
                self._closing = True
                self._stop_on_quit = True
                self.worker.cancel.set()
                self._footer.status.configure(
                    text="Saliendo al terminar la operación..."
                )
            return
        self._shutdown()

    def _shutdown(self) -> None:
        """Para los servicios en segundo plano y cierra al terminar."""
        station = self.station

        def stop(reporter: Reporter) -> None:
            service.shutdown(station, reporter)

        self.run("Parando los servicios...", stop, self._quit, title="Salir")

    def _check_updates(self) -> None:
        """Busca en segundo plano una versión nueva de atril (sin rastro si falla)."""
        if not self.run(
            "Buscando una versión nueva...",
            lambda _: updates.check(),
            self._offer_update,
            quiet=True,
        ):
            self.after(UPDATE_DELAY_MS, self._check_updates)  # había otra lectura

    def _offer_update(self, release: updates.Release | None) -> None:
        """Pregunta si actualizar (o, sin instalador, si ver las novedades)."""
        if release is None or self.closed:
            return
        intro = (
            f"Hay una versión nueva de atril, la {release.version} "
            f"(tienes la {__version__})."
        )
        if updates.installer_folder():
            if release.installer_url is None:
                return  # el instalador se publica unos minutos después: otro día
            if ask_yes_no(
                self,
                "Versión nueva",
                f"{intro} Atril se cerrará, se instalará la nueva y se volverá a "
                "abrir. Si DeepTutor está en marcha, sigue funcionando.",
                "Actualizar",
            ):
                self._update(release)
            return
        if ask_yes_no(
            self,
            "Versión nueva",
            f"{intro} Esta copia no se instaló con el instalador de atril: "
            "actualízala por el mismo medio con que la instalaste.",
            "Ver novedades",
        ):
            webbrowser.open(release.page)

    def _update(self, release: updates.Release) -> None:
        """Descarga el instalador, lo lanza y cierra la ventana."""
        cancel = self.worker.cancel

        def download(reporter: Reporter) -> Path:
            return updates.download_installer(release, reporter, cancel)

        def install(installer: Path) -> None:
            tray.release_mutex()  # el instalador espera a que no exista
            updates.launch_installer(installer)
            self._quit(None)

        self.run(
            "Descargando la versión nueva...",
            download,
            install,
            title=f"Actualizar atril a {release.version}",
        )

    def _tray_command(self, command: TrayCommand) -> None:
        """Atiende una orden del icono."""
        match command:
            case TrayCommand.SHOW:
                self.show_window()
            case TrayCommand.OPEN:
                webbrowser.open(DeepTutor(self.station).frontend_url)
            case TrayCommand.TOGGLE:
                home = self.views["Inicio"]
                if isinstance(home, HomeView):
                    if self._deeptutor_up:
                        home.stop_deeptutor()
                    else:
                        home.start()
            case TrayCommand.BACKUP:
                backups = self.views["Backups"]
                if isinstance(backups, BackupsView):
                    backups.create()
            case TrayCommand.ACTIVITY:
                self.show_window()
                self.show_view("Actividad")
            case TrayCommand.QUIT:
                self.quit_all()

    def _update_tray(self) -> None:
        """Menú y texto del icono según el estado actual."""
        if self.tray is None:
            return
        busy = self.worker.running and not self._quiet
        self.tray.menu = tray_menu(deeptutor_up=self._deeptutor_up, busy=busy)
        status = str(self._footer.status.cget("text")) if busy else ""
        self.tray.set_tooltip(
            tray_tooltip(deeptutor_up=self._deeptutor_up, status=status)
        )

    # --- construcción -----------------------------------------------------------

    def _build(self) -> None:
        """Navegación, apartados y pie de ventana."""
        self.configure(background=style.PAGE)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._sidebar = Sidebar(self, self.show_view)
        self._sidebar.grid(row=0, column=0, sticky="nsw")

        stack = tk.Frame(self, background=style.PAGE)
        stack.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=(16, 8))
        stack.columnconfigure(0, weight=1)
        stack.rowconfigure(0, weight=1)
        self.views: dict[str, View] = {}
        for name, icon, builder in SECTIONS:
            self._sidebar.add(name, icon)
            view = builder(stack, self)
            view.grid(row=0, column=0, sticky="nsew")
            view.grid_remove()
            self.views[name] = view
        self._sidebar.add_links()
        self._footer = Footer(self)
        self._footer.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _remembered_syllabus(self) -> str | None:
        """Temario activo de la última vez (si se guardó)."""
        try:
            data = json.loads(
                self.station.window_state_file.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None
        value = data.get("temario") if isinstance(data, dict) else None
        return value if isinstance(value, str) else None

    # --- avisos del trabajo en segundo plano ------------------------------------

    def _poll(self) -> None:
        """Reparte los avisos del trabajo y vuelve a programarse."""
        self.worker.poll()
        if self.closed:
            return
        if self._closing and not self.worker.running:
            if self._stop_on_quit:
                self._closing = self._stop_on_quit = False
                self._shutdown()
            else:
                self._quit(None)
                return
        if self.tray is not None:
            for command in self.tray.pending():
                self._tray_command(command)
            self._update_tray()
        if not self.worker.running and not self._idle:
            self._set_idle(True)
            self.on_busy(None)
        if not self.worker.running and time.monotonic() - self._status_at > STATUS_TTL:
            self._status_at = time.monotonic()
            home = self.views["Inicio"]
            if isinstance(home, HomeView):
                home.refresh()
        self.after(POLL_MS, self._poll)

    def on_show(self, title: str | None, findings: list[Finding]) -> None:
        """Las comprobaciones van al detalle de la operación en curso."""
        if self._event is not None:
            self._event.add(findings)

    def on_busy(self, text: str | None) -> None:
        """Muestra la espera en el pie de ventana (no la de las lecturas)."""
        if text is not None and self._quiet:
            return
        bar = self._footer.bar
        if text is None:
            self._footer.status.configure(text="")
            bar.stop()
            bar.grid_remove()
            return
        self._footer.status.configure(text=text)
        if str(bar.cget("mode")) != "indeterminate" or not bar.winfo_ismapped():
            bar.configure(mode="indeterminate")
            bar.grid()
            bar.start(15)

    def on_progress(self, text: str | None, total: int) -> None:
        """Barra de avance de un trabajo medible."""
        if text is None:
            self.on_busy(None)
            return
        self._footer.status.configure(text=text)
        bar = self._footer.bar
        bar.stop()
        bar.configure(mode="determinate", maximum=max(total, 1), value=0)
        bar.grid()

    def on_advance(self, amount: int) -> None:
        """Avanza la barra."""
        self._footer.bar.step(amount)

    # --- auxiliares ---------------------------------------------------------------

    def _finish(self, event: Event | None, exc: Exception | None = None) -> None:
        """Cierra el evento de la operación y lo guarda."""
        if self._event is event:
            self._event = None
        self._quiet = False
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
        if self.hidden and self.tray is not None:
            self.tray.notify(event.title, event.summary, event.level)
        self._expected_change = True  # DeepTutor puede pararse por la operación
        self._loaded.clear()  # la operación puede haber cambiado cualquier dato
        self._status_at = 0.0  # y el estado de los servicios
        self._save(event)
        self._activity_changed()

    def _save(self, event: Event) -> None:
        """Guarda el evento y, si el historial no se puede guardar, avisa una vez."""
        self.activity.save(event)
        if self.activity.error and not self._warned:
            self._warned = True
            self._footer.warn(self.activity.error)

    def _activity_changed(self) -> None:
        """Repinta Actividad si está a la vista."""
        view = self.views["Actividad"]
        if isinstance(view, HistoryView) and view.winfo_ismapped():
            view.refresh()

    def _show_error(self, exc: Exception) -> None:
        """Muestra un error (las cancelaciones, solo en la actividad)."""
        if isinstance(exc, CancelledError) or self._closing or self.hidden:
            return  # oculta: ya lo ha dicho la notificación de la operación
        message = _sentence(str(exc) if isinstance(exc, AtrilError) else repr(exc))
        if isinstance(exc, AtrilError) and exc.log:
            message += "\n\nEl detalle técnico está en Actividad."
        show_message(self, "No se ha podido completar", message, Level.ERROR)

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

    def destroy(self) -> None:
        """Destruye la ventana y quita el icono del área de notificación."""
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
        super().destroy()


def _sentence(text: str) -> str:
    """Primera letra en mayúscula."""
    return text[:1].upper() + text[1:]


def _stopper(station: Station) -> Callable[[Reporter], None]:
    """Trabajo que para DeepTutor."""

    def stop(reporter: Reporter) -> None:
        service.stop(service.installed(station), reporter)

    return stop


def _fit_scale(root: tk.Tk) -> None:
    """Reduce la escala si la ventana fija no cabe en la pantalla.

    La ventana mide :data:`WIDTH` x :data:`HEIGHT` multiplicados por la escala
    de Windows; en un portátil pequeño al 125 % o 150 % no cabría.
    """
    current = style.scale(root)
    room = min(
        root.winfo_screenwidth() * 0.96 / WIDTH,
        (root.winfo_screenheight() - 60) * 0.94 / HEIGHT,
    )
    if current > room > 0:
        root.tk.call("tk", "scaling", room * 96 / 72)


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
        f"carpeta que contiene {STATION_FILE}. Si no, elige o crea una carpeta vacía "
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
    if tray.signal_running():
        return  # ya hay un atril abierto: se muestra ese
    tray.hold_mutex()
    _prepare_windows()
    style.register_fonts()
    station = choose_station()
    if station is None:
        return
    App(station).mainloop()
