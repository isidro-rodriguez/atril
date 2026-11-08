"""Ventana principal de atril.

Pantalla de inicio: estado real de la estación (DeepTutor, Ollama, copias), abrir
DeepTutor en el navegador, pararlo y la actividad reciente. Toda la lógica está en
:mod:`atril.ops`; aquí solo se presenta y se pregunta.
"""

import contextlib
import sys
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from atril import __version__
from atril.checks import Finding, Level
from atril.config import ConfigError, load_station
from atril.config.station import STATION_FILE, Station, init_station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.gui import style
from atril.gui.model import Row, overall, summarize
from atril.gui.worker import Worker
from atril.ops import Reporter, service
from atril.ops.service import Section
from atril.ops.station import persist_station, saved_station

POLL_MS = 100
"""Cada cuánto se reparten los avisos del trabajo en segundo plano."""

TAGLINE = "Aprende. Practica. Avanza."
"""Lema de la cabecera."""


class App(tk.Tk):
    """Ventana principal: barra lateral, cabecera, inicio y barra de estado."""

    def __init__(self, station: Station) -> None:
        """Construye la ventana para ``station`` y lanza la primera comprobación."""
        super().__init__(className="Atril")
        self.station = station
        self.worker = Worker(self)
        self._images = _load_icons(self)
        self.title("Atril")
        self.iconphoto(True, *self._images.values())
        self.minsize(900, 600)
        self.geometry("1120x720")
        style.apply(self)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(POLL_MS, self._poll)
        self.refresh()

    # --- construcción -----------------------------------------------------

    def _build(self) -> None:
        """Barra lateral a la izquierda y contenido a la derecha."""
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar().grid(row=0, column=0, sticky="nsw")
        content = tk.Frame(self, background=style.PAGE)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)
        self._build_banner(content).grid(row=0, column=0, sticky="ew")
        self._build_home(content).grid(row=1, column=0, sticky="ew", padx=20, pady=16)
        self._build_activity(content).grid(
            row=2, column=0, sticky="nsew", padx=20, pady=(0, 16)
        )
        self._build_statusbar().grid(row=1, column=0, columnspan=2, sticky="ew")

    def _build_sidebar(self) -> tk.Frame:
        """Apartados de la aplicación (de momento, solo Inicio)."""
        bar = tk.Frame(self, background=style.SIDEBAR, width=220, padx=10, pady=16)
        bar.grid_propagate(False)
        bar.columnconfigure(0, weight=1)
        bar.rowconfigure(1, weight=1)
        style.label(
            bar,
            "⌂   Inicio",
            background=style.SELECTED,
            font=style.STRONG,
            color=style.NAVY,
            padx=14,
            pady=8,
        ).grid(row=0, column=0, sticky="ew")
        style.label(
            bar,
            f"atril {__version__}",
            background=style.SIDEBAR,
            font=style.CAPTION,
            color=style.MUTED,
            padx=8,
        ).grid(row=2, column=0, sticky="w")
        return bar

    def _build_banner(self, parent: tk.Misc) -> tk.Frame:
        """Cabecera con el icono, el nombre y el lema."""
        banner = tk.Frame(parent, background=style.BANNER, padx=24, pady=16)
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

    def _build_home(self, parent: tk.Misc) -> tk.Frame:
        """Tarjetas de estado general y de accesos rápidos."""
        home = tk.Frame(parent, background=style.PAGE)
        home.columnconfigure(0, weight=3)
        home.columnconfigure(1, weight=2)

        status = style.card(home, "Estado general")
        status.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        status.columnconfigure(0, weight=1)
        self._overall = style.label(
            status, "Comprobando…", background=style.CARD, font=style.STRONG
        )
        self._overall.grid(row=1, column=0, sticky="w")
        self._checked = style.label(
            status, background=style.CARD, font=style.CAPTION, color=style.MUTED
        )
        self._checked.grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._rows = tk.Frame(status, background=style.CARD)
        self._rows.grid(row=3, column=0, sticky="ew")
        self._rows.columnconfigure(2, weight=1)

        actions = style.card(home, "Accesos rápidos")
        actions.grid(row=0, column=1, sticky="nsew")
        actions.columnconfigure(0, weight=1)
        self._buttons = [
            ttk.Button(
                actions,
                text="Abrir DeepTutor",
                style="Accent.TButton",
                command=self.open_deeptutor,
            ),
            ttk.Button(actions, text="Parar DeepTutor", command=self.stop_deeptutor),
            ttk.Button(actions, text="Comprobar estado", command=self.refresh),
            ttk.Button(
                actions, text="Abrir carpeta de la estación", command=self.open_folder
            ),
        ]
        for row, button in enumerate(self._buttons, start=1):
            button.grid(row=row, column=0, sticky="ew", pady=4)
        return home

    def _build_activity(self, parent: tk.Misc) -> tk.Frame:
        """Registro de lo que va haciendo atril."""
        frame = style.card(parent, "Actividad")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        self._log = tk.Text(
            frame,
            height=8,
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

    # --- acciones -----------------------------------------------------------

    def refresh(self) -> None:
        """Comprueba el estado de la estación en segundo plano."""
        self._run(
            "Comprobando el estado...",
            lambda reporter: service.status(self.station, reporter),
            self._show_status,
        )

    def open_deeptutor(self) -> None:
        """Arranca DeepTutor si hace falta y lo abre en el navegador."""

        def opened(url: str) -> None:
            self._append(Level.OK, f"DeepTutor listo: {url}")
            webbrowser.open(url)
            self.refresh()

        self._run(
            "Abriendo DeepTutor (la primera vez tarda unos minutos)...",
            lambda reporter: service.open_url(self.station, reporter),
            opened,
        )

    def stop_deeptutor(self) -> None:
        """Detiene DeepTutor y sus procesos de la estación."""

        def stopped(_: None) -> None:
            self._append(Level.OK, "DeepTutor detenido.")
            self.refresh()

        self._run("Deteniendo DeepTutor...", _stopper(self.station), stopped)

    def open_folder(self) -> None:
        """Abre la carpeta de la estación en el explorador de archivos."""
        webbrowser.open(self.station.root.as_uri())

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
                self._run("Deteniendo DeepTutor...", _stopper(self.station), self._quit)
                return
        self._quit(None)

    # --- trabajo en segundo plano --------------------------------------------

    def _run[T](
        self, text: str, task: Callable[[Reporter], T], on_done: Callable[[T], None]
    ) -> None:
        """Lanza ``task`` si no hay otra en marcha y bloquea los botones mientras."""
        if not self.worker.submit(task, on_done, self._show_error):
            self._append(Level.WARNING, "Espera a que termine la operación en curso.")
            return
        self._set_buttons(enabled=False)
        self.on_busy(text)

    def _poll(self) -> None:
        """Reparte los avisos del trabajo y vuelve a programarse."""
        self.worker.poll()
        if not self.worker.running:
            self._set_buttons(enabled=True)
            if str(self._status.cget("text")) != "Listo":
                self.on_busy(None)
        self.after(POLL_MS, self._poll)

    def on_show(self, title: str | None, findings: list[Finding]) -> None:
        """Escribe las comprobaciones en la actividad."""
        for finding in findings:
            self._append(finding.level, finding.message)

    def on_busy(self, text: str | None) -> None:
        """Muestra la espera en la barra de estado."""
        if text is None:
            self._status.configure(text="Listo")
            self._bar.stop()
            self._bar.grid_remove()
            return
        self._status.configure(text=text)
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

    # --- presentación ---------------------------------------------------------

    def _show_status(self, sections: list[Section]) -> None:
        """Pinta el resumen del estado."""
        rows = summarize(sections)
        level, text = overall(rows)
        self._overall.configure(
            text=f"{style.LEVEL_SYMBOLS[level]}  {text}",
            foreground=style.LEVEL_COLORS[level],
        )
        self._checked.configure(text=f"Comprobado a las {time.strftime('%H:%M')}")
        for widget in self._rows.winfo_children():
            widget.destroy()
        for index, row in enumerate(rows):
            self._status_row(index, row)

    def _status_row(self, index: int, row: Row) -> None:
        """Una fila: símbolo de nivel, sección y mensaje."""
        cells = (
            (
                style.LEVEL_SYMBOLS[row.level],
                style.STRONG,
                style.LEVEL_COLORS[row.level],
            ),
            (row.title, style.STRONG, style.TEXT),
            (row.message, style.BODY, style.TEXT),
        )
        for column, (text, font, color) in enumerate(cells):
            style.label(
                self._rows,
                text,
                background=style.CARD,
                font=font,
                color=color,
                wraplength=440 if column == 2 else 0,
            ).grid(row=index, column=column, sticky="nw", padx=(0, 10), pady=3)

    def _show_error(self, exc: Exception) -> None:
        """Muestra un error en la actividad y en un diálogo."""
        message = str(exc) if isinstance(exc, AtrilError) else repr(exc)
        self._append(Level.ERROR, message)
        detail = ""
        if isinstance(exc, AtrilError) and exc.log:
            detail = (
                "\n\nÚltimas líneas de "
                + exc.log_title
                + ":\n"
                + "\n".join(exc.log[-10:])
            )
            for line in exc.log:
                self._append(Level.INFO, line)
        text = message[:1].upper() + message[1:] + detail
        messagebox.showerror("Atril", text, parent=self)

    def _append(self, level: Level, message: str) -> None:
        """Añade una línea a la actividad."""
        self._log.configure(state="normal")
        self._log.insert("end", time.strftime("%H:%M:%S  "), "time")
        line = f"{style.LEVEL_SYMBOLS[level]} {message}\n"
        self._log.insert("end", line, level.value)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_buttons(self, *, enabled: bool) -> None:
        """Activa o desactiva los accesos rápidos (salvo abrir la carpeta)."""
        for button in self._buttons[:-1]:
            button.state(["!disabled"] if enabled else ["disabled"])

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


# --- arranque ------------------------------------------------------------------


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
