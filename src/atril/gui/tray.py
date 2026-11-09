"""Icono de atril en el área de notificación de Windows.

Solo biblioteca estándar: ``Shell_NotifyIconW`` y una ventana oculta con
``ctypes``, en un hilo propio que recibe los clics del icono y el aviso de una
segunda instancia. Las órdenes del menú se dejan en una cola que la ventana de
Tk vacía en su sondeo, porque Tk solo admite llamadas desde su hilo. El menú
(:attr:`Tray.menu`) lo calcula la ventana con :func:`atril.gui.model.tray_menu`.

Fuera de Windows no hay icono: :func:`create` devuelve ``None`` y la ventana se
cierra como siempre.
"""

import contextlib
import queue
import sys
import threading
import time
from importlib import resources

from atril.checks import Level
from atril.gui.model import TrayCommand, TrayMenu

WINDOW_CLASS = "AtrilTrayWindow"
"""Clase de la ventana oculta: una segunda instancia la busca para avisar."""

MUTEX = "AtrilGui"
"""Mutex de la ventana: el instalador (``AppMutex``) pide cerrar atril si existe."""
SETUP_MUTEX = "AtrilSetup"
"""Mutex del instalador (``SetupMutex``): existe mientras se instala atril."""

_CALLBACK = 0x8001  # WM_APP + 1: clics en el icono
_SHOW = 0x8002  # WM_APP + 2: una segunda instancia pide mostrar la ventana


class Tray:
    """Icono, menú y notificaciones de atril (solo Windows).

    Los métodos públicos se llaman desde el hilo de Tk; los clics llegan a
    :attr:`commands`.
    """

    def __init__(self) -> None:
        """Prepara el hilo; :meth:`start` crea la ventana oculta."""
        self.commands: queue.Queue[TrayCommand] = queue.Queue()
        """Órdenes pendientes para la ventana de Tk."""
        self.menu: TrayMenu = ()
        """Menú que se muestra con el botón derecho."""
        self._tip = "Atril"
        self._visible = False
        self._hwnd = 0
        self._icon = 0
        self._ready = threading.Event()
        self._files = contextlib.ExitStack()
        self._thread = threading.Thread(
            target=self._loop, name="atril-icono", daemon=True
        )

    def start(self) -> bool:
        """Crea la ventana oculta; ``False`` si no se ha podido."""
        self._thread.start()
        self._ready.wait(5)
        return bool(self._hwnd)

    def pending(self) -> list[TrayCommand]:
        """Órdenes recibidas desde la última llamada."""
        found = []
        with contextlib.suppress(queue.Empty):
            while True:
                found.append(self.commands.get_nowait())
        return found

    def show_icon(self) -> None:
        """Pone el icono en el área de notificación."""
        if not self._visible:
            self._visible = _notify_icon(self, _NIM_ADD, _NIF_BASE)

    def hide_icon(self) -> None:
        """Quita el icono."""
        if self._visible:
            _notify_icon(self, _NIM_DELETE, 0)
            self._visible = False

    def set_tooltip(self, text: str) -> None:
        """Texto al pasar el ratón (solo se envía si cambia)."""
        if text != self._tip:
            self._tip = text
            if self._visible:
                _notify_icon(self, _NIM_MODIFY, _NIF_TIP)

    def notify(self, title: str, text: str, level: Level = Level.INFO) -> None:
        """Notificación del sistema (solo con el icono a la vista)."""
        if self._visible:
            _notify_icon(self, _NIM_MODIFY, _NIF_INFO, (title, text, level))

    def stop(self) -> None:
        """Quita el icono, cierra la ventana oculta y espera al hilo."""
        if self._hwnd:
            _post(self._hwnd, _WM_CLOSE)
            self._thread.join(2)
        self._files.close()

    def _loop(self) -> None:
        """Hilo del icono: ventana oculta y su bucle de mensajes."""
        try:
            _run(self)
        finally:
            self._ready.set()

    def _icon_path(self) -> str:
        """Ruta en disco de ``atril.ico`` (se libera en :meth:`stop`)."""
        ico = resources.files("atril.gui") / "recursos" / "atril.ico"
        return str(self._files.enter_context(resources.as_file(ico)))


def create() -> Tray | None:
    """Icono de atril, o ``None`` fuera de Windows o si no se puede crear."""
    if sys.platform != "win32":
        return None
    tray = Tray()
    return tray if tray.start() else None


def signal_running() -> bool:
    """Si ya hay un atril abierto, le pide que se muestre y devuelve ``True``."""
    if sys.platform != "win32":
        return False
    hwnd = _user32.FindWindowW(WINDOW_CLASS, None)
    if not hwnd:
        return False
    _user32.AllowSetForegroundWindow(_ASFW_ANY)
    _post(hwnd, _SHOW)
    return True


def hold_mutex() -> None:
    """Crea el mutex :data:`MUTEX`, que Windows libera al cerrar el proceso."""
    if sys.platform == "win32":
        _mutexes.append(_kernel32.CreateMutexW(None, False, MUTEX))


def release_mutex() -> None:
    """Libera el mutex (antes de lanzar el instalador, que lo comprueba)."""
    while _mutexes:
        handle = _mutexes.pop()
        if sys.platform == "win32" and handle:
            _kernel32.CloseHandle(handle)


def setup_running() -> bool:
    """El instalador de atril está en marcha (su mutex existe)."""
    if sys.platform != "win32":
        return False
    handle = _kernel32.OpenMutexW(_SYNCHRONIZE, False, SETUP_MUTEX)
    if not handle:
        return False
    _kernel32.CloseHandle(handle)
    return True


def wait_for_setup(timeout: float = 180.0) -> bool:
    """Espera a que termine el instalador; ``False`` si sigue al acabar el plazo."""
    deadline = time.monotonic() + timeout
    while setup_running():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)
    return True


_SYNCHRONIZE = 0x00100000

_mutexes: list[int] = []
"""Mutex creados (se conservan mientras vive el proceso)."""


# --- Win32 ---------------------------------------------------------------------------

_NIM_ADD, _NIM_MODIFY, _NIM_DELETE = 0, 1, 2
_NIF_MESSAGE, _NIF_ICON, _NIF_TIP, _NIF_INFO = 0x1, 0x2, 0x4, 0x10
_NIF_BASE = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
_NIIF = {Level.WARNING: 0x2, Level.ERROR: 0x3}  # el resto, sin icono de nivel
_WM_CLOSE, _WM_DESTROY, _WM_NULL = 0x0010, 0x0002, 0x0000
_WM_LBUTTONUP, _WM_RBUTTONUP = 0x0202, 0x0205
_MF_GRAYED, _MF_SEPARATOR = 0x1, 0x800
_TPM_RIGHTBUTTON, _TPM_NONOTIFY, _TPM_RETURNCMD = 0x2, 0x80, 0x100
_IMAGE_ICON, _LR_LOADFROMFILE = 1, 0x10
_SM_CXSMICON, _SM_CYSMICON = 49, 50
_ASFW_ANY = 0xFFFFFFFF

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _LRESULT = ctypes.c_ssize_t
    _WNDPROC = ctypes.WINFUNCTYPE(
        _LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class _Guid(ctypes.Structure):
        _fields_ = (
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        )

    class _NotifyIconData(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", _Guid),
            ("hBalloonIcon", wintypes.HICON),
        )

    class _WndClass(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        )

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _HWND, _UINT, _INT = wintypes.HWND, wintypes.UINT, ctypes.c_int
    for _name, _args, _result in (
        ("RegisterClassExW", (ctypes.POINTER(_WndClass),), wintypes.ATOM),
        (
            "CreateWindowExW",
            (wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
            + (_INT,) * 4
            + (_HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID),
            _HWND,
        ),
        ("DefWindowProcW", (_HWND, _UINT, wintypes.WPARAM, wintypes.LPARAM), _LRESULT),
        (
            "GetMessageW",
            (ctypes.POINTER(wintypes.MSG), _HWND, _UINT, _UINT),
            wintypes.BOOL,
        ),
        ("TranslateMessage", (ctypes.POINTER(wintypes.MSG),), wintypes.BOOL),
        ("DispatchMessageW", (ctypes.POINTER(wintypes.MSG),), _LRESULT),
        (
            "PostMessageW",
            (_HWND, _UINT, wintypes.WPARAM, wintypes.LPARAM),
            wintypes.BOOL,
        ),
        ("PostQuitMessage", (_INT,), None),
        ("DestroyWindow", (_HWND,), wintypes.BOOL),
        ("FindWindowW", (wintypes.LPCWSTR, wintypes.LPCWSTR), _HWND),
        ("RegisterWindowMessageW", (wintypes.LPCWSTR,), _UINT),
        ("CreatePopupMenu", (), wintypes.HMENU),
        (
            "AppendMenuW",
            (wintypes.HMENU, _UINT, wintypes.WPARAM, wintypes.LPCWSTR),
            wintypes.BOOL,
        ),
        ("SetMenuDefaultItem", (wintypes.HMENU, _UINT, _UINT), wintypes.BOOL),
        (
            "TrackPopupMenu",
            (wintypes.HMENU, _UINT, _INT, _INT, _INT, _HWND, wintypes.LPVOID),
            _INT,
        ),
        ("DestroyMenu", (wintypes.HMENU,), wintypes.BOOL),
        ("GetCursorPos", (ctypes.POINTER(wintypes.POINT),), wintypes.BOOL),
        ("SetForegroundWindow", (_HWND,), wintypes.BOOL),
        ("AllowSetForegroundWindow", (wintypes.DWORD,), wintypes.BOOL),
        (
            "LoadImageW",
            (wintypes.HINSTANCE, wintypes.LPCWSTR, _UINT, _INT, _INT, _UINT),
            wintypes.HANDLE,
        ),
        ("DestroyIcon", (wintypes.HICON,), wintypes.BOOL),
        ("GetSystemMetrics", (_INT,), _INT),
    ):
        _function = getattr(_user32, _name)
        _function.argtypes = _args
        _function.restype = _result
    _shell32.Shell_NotifyIconW.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(_NotifyIconData),
    )
    _shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    _kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.OpenMutexW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    def _post(hwnd: int, message: int) -> None:
        """Deja ``message`` en la cola de la ventana oculta."""
        _user32.PostMessageW(hwnd, message, 0, 0)

    def _notify_icon(
        tray: Tray,
        action: int,
        flags: int,
        info: tuple[str, str, Level] | None = None,
    ) -> bool:
        """Llama a ``Shell_NotifyIconW`` con el estado de ``tray``."""
        data = _NotifyIconData()
        data.cbSize = ctypes.sizeof(_NotifyIconData)
        data.hWnd = tray._hwnd
        data.uID = 1
        data.uFlags = flags
        data.uCallbackMessage = _CALLBACK
        data.hIcon = tray._icon
        data.szTip = tray._tip[:127]
        if info is not None:
            title, text, level = info
            data.szInfoTitle = title[:63]
            data.szInfo = text[:255]
            data.dwInfoFlags = _NIIF.get(level, 0)
        return bool(_shell32.Shell_NotifyIconW(action, ctypes.byref(data)))

    def _popup(tray: Tray, hwnd: int) -> None:
        """Muestra el menú en el ratón y deja la orden elegida en la cola."""
        menu = _user32.CreatePopupMenu()
        commands: dict[int, TrayCommand] = {}
        for item in tray.menu:
            if item is None:
                _user32.AppendMenuW(menu, _MF_SEPARATOR, 0, None)
                continue
            ident = len(commands) + 1
            commands[ident] = item.command
            flags = 0 if item.enabled else _MF_GRAYED
            _user32.AppendMenuW(menu, flags, ident, item.text)
            if item.default:
                _user32.SetMenuDefaultItem(menu, ident, 0)
        point = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        _user32.SetForegroundWindow(hwnd)  # si no, el menú no se cierra al salir
        chosen = _user32.TrackPopupMenu(
            menu,
            _TPM_RIGHTBUTTON | _TPM_NONOTIFY | _TPM_RETURNCMD,
            point.x,
            point.y,
            0,
            hwnd,
            None,
        )
        _post(hwnd, _WM_NULL)
        _user32.DestroyMenu(menu)
        if chosen in commands:
            tray.commands.put(commands[chosen])

    _trays: dict[int, Tray] = {}
    """Icono de cada ventana oculta (el procedimiento es uno para la clase)."""
    _TASKBAR_CREATED = _user32.RegisterWindowMessageW("TaskbarCreated")

    def _procedure(hwnd: int, message: int, wparam: int, lparam: int) -> int:
        """Mensajes de las ventanas ocultas: clics, otra instancia y cierre."""
        tray = _trays.get(hwnd)
        if tray is None:
            return _user32.DefWindowProcW(hwnd, message, wparam, lparam)
        if message == _CALLBACK:
            if lparam == _WM_LBUTTONUP:
                _user32.SetForegroundWindow(hwnd)  # permite traer la ventana
                tray.commands.put(TrayCommand.SHOW)
            elif lparam == _WM_RBUTTONUP:
                _popup(tray, hwnd)
            return 0
        if message == _SHOW:
            tray.commands.put(TrayCommand.SHOW)
            return 0
        if message == _TASKBAR_CREATED and tray._visible:  # Explorer reiniciado
            _notify_icon(tray, _NIM_ADD, _NIF_BASE)
            return 0
        if message == _WM_CLOSE:
            tray.hide_icon()
            _user32.DestroyWindow(hwnd)
            return 0
        if message == _WM_DESTROY:
            del _trays[hwnd]
            _user32.PostQuitMessage(0)
            return 0
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    _PROCEDURE = _WNDPROC(_procedure)
    """Se registra una sola vez y vive lo que el proceso (Windows lo llama)."""
    _registered = False

    def _register(instance: int) -> None:
        """Registra la clase de la ventana oculta (una vez por proceso)."""
        global _registered
        if _registered:
            return
        window_class = _WndClass()
        window_class.cbSize = ctypes.sizeof(_WndClass)
        window_class.lpfnWndProc = _PROCEDURE
        window_class.hInstance = instance
        window_class.lpszClassName = WINDOW_CLASS
        _registered = bool(_user32.RegisterClassExW(ctypes.byref(window_class)))

    def _run(tray: Tray) -> None:
        """Crea la ventana oculta y atiende sus mensajes hasta cerrarla."""
        instance = _kernel32.GetModuleHandleW(None)
        _register(instance)
        hwnd = _user32.CreateWindowExW(
            0, WINDOW_CLASS, "Atril", 0, 0, 0, 0, 0, None, None, instance, None
        )
        if not hwnd:
            return
        _trays[hwnd] = tray
        with contextlib.suppress(OSError):
            tray._icon = (
                _user32.LoadImageW(
                    None,
                    tray._icon_path(),
                    _IMAGE_ICON,
                    _user32.GetSystemMetrics(_SM_CXSMICON),
                    _user32.GetSystemMetrics(_SM_CYSMICON),
                    _LR_LOADFROMFILE,
                )
                or 0
            )
        tray._hwnd = hwnd
        tray._ready.set()
        message = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(message))
            _user32.DispatchMessageW(ctypes.byref(message))
        if tray._icon:
            _user32.DestroyIcon(tray._icon)
        tray._hwnd = 0

else:  # pragma: no cover - sin área de notificación

    def _post(hwnd: int, message: int) -> None:
        """Sin Windows no hay ventana oculta."""

    def _notify_icon(
        tray: Tray,
        action: int,
        flags: int,
        info: tuple[str, str, Level] | None = None,
    ) -> bool:
        """Sin Windows no hay icono."""
        return False

    def _run(tray: Tray) -> None:
        """Sin Windows no hay ventana oculta."""
