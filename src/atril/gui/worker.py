"""Trabajos en segundo plano para la GUI.

Tk solo admite llamadas desde su propio hilo: el trabajo corre en un hilo aparte
y envía sus avisos por una cola que la ventana vacía con :meth:`Worker.poll`
(llamado periódicamente con ``after``). Hay un solo trabajo a la vez.
"""

import contextlib
import queue
import threading
from collections.abc import Callable, Generator, Sequence
from typing import Any, Protocol

from atril.checks import Finding
from atril.ops import Advance, Reporter, Update


class Listener(Protocol):
    """Lo que la ventana hace con cada aviso (siempre en el hilo de Tk)."""

    def on_show(self, title: str | None, findings: list[Finding]) -> None:
        """Comprobaciones nuevas."""
        ...

    def on_busy(self, text: str | None) -> None:
        """Empieza (texto) o termina (``None``) una espera."""
        ...

    def on_progress(self, text: str | None, total: int) -> None:
        """Empieza (texto) o termina (``None``) un trabajo medible."""
        ...

    def on_advance(self, amount: int) -> None:
        """Avance del trabajo medible."""
        ...


class QueueReporter:
    """:class:`atril.ops.Reporter` que deja los avisos en una cola."""

    def __init__(self, events: queue.Queue[tuple[str, Any]]) -> None:
        """Usa ``events`` como cola de salida."""
        self._events = events
        self._waits: list[str] = []
        """Esperas anidadas: al acabar una, vuelve el texto de la anterior."""

    def show(self, findings: Sequence[Finding], title: str | None = None) -> None:
        """Encola las comprobaciones."""
        self._events.put(("show", (title, list(findings))))

    @contextlib.contextmanager
    def busy(self, text: str) -> Generator[Update]:
        """Encola el principio, los cambios y el final de la espera."""
        self._waits.append(text)
        self._events.put(("busy", text))

        def update(new: str) -> None:
            self._waits[-1] = new
            self._events.put(("busy", new))

        try:
            yield update
        finally:
            self._waits.pop()
            self._events.put(("busy", self._waits[-1] if self._waits else None))

    @contextlib.contextmanager
    def progress(self, text: str, total: int) -> Generator[Advance]:
        """Encola el trabajo medible y su avance."""
        self._events.put(("progress", (text, total)))
        try:
            yield lambda amount: self._events.put(("advance", amount))
        finally:
            self._events.put(("progress", (None, 0)))


class Worker:
    """Ejecuta un trabajo cada vez en un hilo y reparte sus avisos."""

    def __init__(self, listener: Listener) -> None:
        """Prepara la cola; ``listener`` recibe los avisos en :meth:`poll`."""
        self._listener = listener
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.cancel = threading.Event()
        """Se activa para pedir al trabajo que pare en un punto seguro."""

    @property
    def running(self) -> bool:
        """Hay un trabajo en marcha (o con avisos aún sin repartir)."""
        return self._thread is not None

    def submit[T](
        self,
        task: Callable[[Reporter], T],
        on_done: Callable[[T], None],
        on_error: Callable[[Exception], None],
    ) -> bool:
        """Lanza ``task``; devuelve ``False`` si ya hay otro trabajo en marcha.

        ``on_done`` y ``on_error`` se llaman desde :meth:`poll`, en el hilo de Tk.
        """
        if self.running:
            return False
        self.cancel.clear()
        reporter = QueueReporter(self._events)

        def run() -> None:
            try:
                result = task(reporter)
            except Exception as exc:  # se muestra en la ventana, no se pierde
                self._events.put(("error", (on_error, exc)))
            else:
                self._events.put(("done", (on_done, result)))

        self._thread = threading.Thread(target=run, name="atril-trabajo", daemon=True)
        self._thread.start()
        return True

    def poll(self) -> None:
        """Reparte los avisos pendientes; al final del trabajo, llama a su callback."""
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                return
            match kind:
                case "show":
                    self._listener.on_show(*payload)
                case "busy":
                    self._listener.on_busy(payload)
                case "progress":
                    self._listener.on_progress(*payload)
                case "advance":
                    self._listener.on_advance(payload)
                case _:
                    self._thread = None
                    callback, value = payload
                    callback(value)
