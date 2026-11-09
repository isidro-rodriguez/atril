r"""Capturas de la web desde la ventana real de atril, con una estación de ejemplo.

Forma parte de la publicación: ``docs.yml`` lo ejecuta en Windows con el código de
cada versión publicada (no es una herramienta de uso manual)::

    uv run --with pillow python scripts/capturas.py <carpeta>

Tres pasos separados:

1. :func:`prepare` crea la estación de ejemplo: una alumna de 2.º de
   Bachillerato de Ciencias con un temario por asignatura, copias, verificaciones
   y actividad, todo con fechas fijas para que las capturas sean reproducibles.
2. :func:`open_window` abre la ventana real con los servicios simulados
   (DeepTutor, Ollama y herramientas en marcha, sin buscar actualizaciones).
3. :func:`capture` recorre los apartados: espera a que cada uno haya cargado (con
   un plazo máximo), lo captura y, al final, :func:`validate` comprueba todas las
   imágenes antes de sustituir las de ``<carpeta>``.

Cualquier fallo (un apartado que no carga, un error en la ventana o en segundo
plano, una imagen incompleta) termina con código distinto de cero y no deja
capturas a medias. En la CI de Windows la estación vive en ``D:\Estudio`` y las
copias en ``D:\Copias\Atril`` (las rutas que se ven en la web), que el runner
aísla: si ya existen, falla sin tocarlas, y al terminar se borran. En cualquier
otro caso, todo va a una carpeta temporal que se borra sola.
"""

import datetime as dt
import functools
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
import tomllib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SIZE = (1024, 700)
"""Tamaño de cada captura: el de la ventana a 100 %."""

MIN_BYTES = 20_000
"""Tamaño mínimo razonable de un PNG de la ventana (uno vacío ocupa mucho menos)."""

TIMEOUT = 60.0
"""Segundos máximos para que un apartado termine de cargar."""

NOW = dt.datetime(2026, 11, 9, 18, 30)
"""Momento fijo de las capturas: fechas y «Hoy/Ayer» no cambian entre ejecuciones."""

SHOTS = ("inicio", "temarios", "biblioteca", "backups", "actividad", "ajustes-atril")
"""Ficheros que genera (y que la web usa)."""

PHYSICS = {
    # KB: (vinculante, descripción, patrones de id, documentos)
    "fisica-teoria": (
        True,
        "Apuntes de clase y formulario",
        ["tema-*", "formulario-*"],
        [
            "Tema 1 - Campo gravitatorio",
            "Tema 2 - Campo eléctrico",
            "Tema 3 - Campo magnético",
            "Tema 4 - Inducción electromagnética",
            "Tema 5 - Movimiento ondulatorio",
            "Tema 6 - Óptica geométrica",
            "Tema 7 - Física relativista",
            "Tema 8 - Física cuántica",
            "Tema 9 - Física nuclear",
            "Formulario de Física",
        ],
    ),
    "fisica-problemas": (
        True,
        "Exámenes y problemas resueltos",
        ["problemas-*", "examenes-*", "olimpiada-*"],
        [
            "Problemas resueltos PAU 2023",
            "Problemas resueltos PAU 2024",
            "Problemas resueltos PAU 2025",
            "Exámenes del instituto 2025-2026",
            "Olimpiada de Física 2024 - fase local",
            "Olimpiada de Física 2025 - fase local",
        ],
    ),
    "fisica-divulgacion": (
        False,
        "Lecturas para ampliar (no entran en el examen)",
        ["divulgacion-*"],
        [
            "Divulgación - Breve historia de la gravedad",
            "Divulgación - Relatividad sin fórmulas",
            "Divulgación - Qué es un cuanto",
            "Divulgación - Ondas gravitacionales",
            "Divulgación - Física de partículas",
        ],
    ),
    "fisica-normativa": (
        True,
        "Currículo y criterios de la PAU",
        ["real-decreto-*", "criterios-*"],
        ["Criterios de corrección PAU de Física"],
    ),
}
"""KB de Física: la de una alumna entusiasta, con fuentes variadas."""

PENDING = {"fisica-divulgacion": 2}
"""Fuentes sin indexar al final de cada KB (las demás, indexadas)."""

SUBJECTS = {
    "Física": [],
    "Matemáticas II": [
        "Tema 1 - Matrices",
        "Tema 2 - Determinantes",
        "Tema 3 - Sistemas de ecuaciones",
        "Tema 4 - Geometría en el espacio",
        "Tema 5 - Límites y continuidad",
        "Tema 6 - Derivadas",
        "Tema 7 - Integrales",
        "Tema 8 - Probabilidad",
        "Exámenes PAU resueltos",
    ],
    "Química": [
        "Tema 1 - Estructura atómica",
        "Tema 2 - Enlace químico",
        "Tema 3 - Cinética y equilibrio",
        "Tema 4 - Ácidos y bases",
        "Tema 5 - Reacciones redox",
        "Tema 6 - Química orgánica",
        "Formulación inorgánica",
    ],
    "Biología": [
        "Tema 1 - Bioelementos y biomoléculas",
        "Tema 2 - La célula",
        "Tema 3 - Metabolismo",
        "Tema 4 - Genética molecular",
        "Tema 5 - Microbiología",
        "Tema 6 - Inmunología",
    ],
    "Historia de España": [
        "Bloque 1 - De la Prehistoria a la Edad Moderna",
        "Bloque 2 - El siglo XIX",
        "Bloque 3 - La Segunda República y la Guerra Civil",
        "Bloque 4 - El franquismo",
        "Bloque 5 - La Transición y la democracia",
    ],
    "Lengua Castellana y Literatura II": [
        "Comentario de texto - Guía",
        "Sintaxis de la oración compuesta",
        "Literatura del siglo XX",
        "Lecturas obligatorias",
    ],
    "Historia de la Filosofía": [
        "Platón",
        "Aristóteles",
        "Descartes",
        "Kant",
        "Nietzsche",
    ],
    "Inglés II": [
        "Grammar review",
        "Writing - Opinion essays",
        "Exámenes PAU de inglés",
    ],
}
"""Temarios de ejemplo; Física (el que más fuentes tiene) es el activo."""

BACKUPS = (("20261019-194000", 112), ("20261026-200500", 117), ("20261102-185500", 121))
"""Copias de ejemplo: fecha (nombre) y tamaño en MB; la última se hace aparte."""

ACTIVITY = (
    (50, "Arrancar", "ok", "DeepTutor en marcha.", ["DeepTutor en marcha."]),
    (
        27,
        "Buscar versiones nuevas",
        "aviso",
        "real-decreto-243-2022: hay una versión nueva; la anterior queda en el "
        "histórico.",
        [],
    ),
    (
        24,
        "Indexar Matemáticas II",
        "ok",
        "9 fuentes indexadas.",
        ["tema-7-integrales indexada (4 min).", "9 fuentes indexadas."],
    ),
    (
        20,
        "Hacer backup",
        "ok",
        "Backup completado correctamente (124 MB).",
        ["Copia verificada: 3.482 ficheros.", "Backup completado correctamente."],
    ),
    (
        3,
        "Añadir fuentes a Física",
        "ok",
        "2 fuentes añadidas.",
        ["Problemas resueltos PAU 2025 añadida.", "Real Decreto 243/2022 añadida."],
    ),
    (
        1,
        "Comprobar backups",
        "ok",
        "Backup más reciente verificado.",
        ["Copias: 4 copias, la más reciente de ayer, verificada."],
    ),
)
"""Actividad de ejemplo: horas antes de :data:`NOW`, título, nivel, resumen, detalle."""


# --- 1. datos ------------------------------------------------------------------------


class CaptureError(Exception):
    """Fallo de la generación de capturas: no se publica ninguna."""


@contextmanager
def workspace() -> Iterator[tuple[Path, Path, Path]]:
    """Estación, destino de las copias y carpeta de trabajo, borrados al terminar."""
    with tempfile.TemporaryDirectory(prefix="atril-capturas-") as temp:
        work = Path(temp)
        if sys.platform == "win32" and os.environ.get("GITHUB_ACTIONS") == "true":
            root, copies = Path(r"D:\Estudio"), Path(r"D:\Copias\Atril")
            created = [root, copies.parent]
        else:
            root, copies = work / "Estudio", work / "Copias" / "Atril"
            created = []
        for folder in created:
            if folder.exists():
                raise CaptureError(f"{folder} ya existe: no se toca.")
        try:
            copies.mkdir(parents=True)
            yield root, copies, work
        finally:
            for folder in created:
                shutil.rmtree(folder, ignore_errors=True)


def prepare(root: Path, copies: Path, work: Path) -> None:
    """Crea la estación de ejemplo en ``root`` (las copias, en ``copies``)."""
    from atril.config import load_station, load_syllabus
    from atril.config.station import init_station
    from atril.ops import syllabus as syllabus_ops

    init_station(root)
    config = root / "atril.toml"
    text = config.read_text(encoding="utf-8")
    start = text.index("destinos = [")
    end = text.index("]", start) + 1
    text = text[:start] + f"destinos = [{str(copies)!r}]" + text[end:]
    config.write_text(
        text
        + '\n[deeptutor.llm]\nproveedor = "claude_code"\nmodelo = "claude-code/opus"\n'
        + '\n[ollama]\nembedding = "qwen3-embedding:8b"\ndimension = 4096\n',
        encoding="utf-8",
    )
    station = load_station(root)

    downloads = work / "pdf"
    downloads.mkdir()
    for index, (name, documents) in enumerate(SUBJECTS.items()):
        syllabus = syllabus_ops.create(station, name)
        groups = {None: documents}
        if name == "Física":
            _physics_kbs(syllabus.root)
            groups = {kb: docs for kb, (*_, docs) in PHYSICS.items()}
        for kb_id, group in groups.items():
            for document in group:
                pdf = downloads / f"{document}.pdf"
                seed = hashlib.sha256(f"{name}/{document}".encode()).digest()
                pdf.write_bytes(b"%PDF-1.7 " + seed * 64)  # contenido fijo
                syllabus_ops.add_source(
                    load_syllabus(syllabus.root), str(pdf), title=document, kb_id=kb_id
                )
        if name == "Física":
            syllabus_ops.add_source(  # declarada, aún sin descargar
                load_syllabus(syllabus.root),
                "https://www.boe.es/buscar/pdf/2022/BOE-A-2022-6008-consolidado.pdf",
                title="Real Decreto 243/2022 (currículo de Bachillerato)",
                kb_id="fisica-normativa",
            )
        _index(
            station,
            load_syllabus(syllabus.root),
            index,
        )
    _backups(station, copies)
    _activity(station)
    (station.data_dir / "atril" / "ventana.json").write_text(
        json.dumps({"temario": "fisica"}), encoding="utf-8"
    )


def _physics_kbs(root: Path) -> None:
    """Sustituye la KB única del temario nuevo por las de :data:`PHYSICS`."""
    text = (root / "temario.toml").read_text(encoding="utf-8")
    text = text[: text.index("[[kb]]")]
    for kb_id, (binding, description, patterns, _) in PHYSICS.items():
        text += (
            f"[[kb]]\nid = {kb_id!r}\nvinculante = {str(binding).lower()}\n"
            f"fuentes = {patterns!r}\ndescripcion = {description!r}\n\n"
        )
    (root / "temario.toml").write_text(text.replace("'", '"'), encoding="utf-8")


def _index(station, syllabus, order: int) -> None:
    """Marca como indexadas todas las fuentes salvo las de :data:`PENDING`."""
    from atril.knowledge import IndexedSource, Ledger, content_digest, ledger_path

    ledger = Ledger(ledger_path(syllabus))
    for kb in syllabus.knowledge_bases:
        sources = syllabus.sources_of(kb)
        for source in sources[: len(sources) - PENDING.get(kb.id, 0)]:
            path = syllabus.source_path(source)
            if path is None or not path.exists():
                continue
            when = NOW - dt.timedelta(days=12 - order, hours=3)
            ledger.kb(kb.id).sources[source.id] = IndexedSource(
                file=path.name,
                sha256=content_digest(source, path),
                indexed_at=when.isoformat(timespec="seconds"),
                minutes=3.5,
            )
        kb_dir = station.kb_dir(kb.id)
        kb_dir.mkdir(parents=True, exist_ok=True)
        run = {"state": "completed", "task_id": f"ejemplo-{kb.id}"}
        (kb_dir / ".indexing-run.json").write_text(json.dumps(run), encoding="utf-8")
    ledger.save()


def _backups(station, copies: Path) -> None:
    """Copias de ejemplo (ficheros del tamaño indicado) y sus verificaciones."""
    stamps = [*BACKUPS, ((NOW - dt.timedelta(hours=20)).strftime("%Y%m%d-%H%M%S"), 124)]
    entries = {}
    for number, (stamp, megabytes) in enumerate(stamps):
        archive = copies / f"atril-{stamp}.zip"
        with archive.open("wb") as out:
            out.truncate(megabytes * 1_000_000)
        info = archive.stat()
        if number >= len(stamps) - 2:  # las dos últimas, verificadas
            when = dt.datetime.strptime(stamp, "%Y%m%d-%H%M%S") + dt.timedelta(
                minutes=4
            )
            entries[str(archive)] = {
                "ok": True,
                "fecha": when.isoformat(timespec="seconds"),
                "tamano": info.st_size,
                "modificado": info.st_mtime_ns,
            }
    station.verifications_file.parent.mkdir(parents=True, exist_ok=True)
    station.verifications_file.write_text(
        json.dumps({"version": 1, "copias": entries}, indent=2), encoding="utf-8"
    )


def _activity(station) -> None:
    """Historial de ejemplo de la ventana."""
    lines = []
    for number, (hours, title, level, summary, detail) in enumerate(ACTIVITY):
        when = (NOW - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
        lines.append(
            json.dumps(
                {
                    "title": title,
                    "category": "general",
                    "level": level,
                    "summary": summary,
                    "detail": [[level, line] for line in detail],
                    "when": when,
                    "id": f"ejemplo{number:05d}",
                    "running": False,
                },
                ensure_ascii=False,
            )
        )
    station.activity_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- 2. ventana ----------------------------------------------------------------------


def open_window(root: Path):
    """Ventana real de atril con los servicios simulados y el momento fijo."""
    import atril.gui.app as app_module
    import atril.gui.backups as backups_view
    import atril.gui.history as history_view
    import atril.gui.home as home
    from atril.config import load_station
    from atril.deeptutor import Assistant
    from atril.gui import activity
    from atril.gui.model import Facts
    from atril.ops import updates

    home.load_facts = lambda station: Facts(
        deeptutor_installed=True,
        backend_up=True,
        frontend_up=True,
        ollama_installed=True,
        ollama_running=True,
        ollama_ours=True,
        ollama_models=("qwen3-embedding:8b",),
        tools=dict.fromkeys(("git", "uv", "node", "npm", "python", "claude"), True),
        assistant=Assistant("claude_code", "claude-code/opus", False),
        ollama_required=True,
    )
    updates.check = lambda current="": None
    fixed = functools.partial(activity.when_label, now=NOW)
    history_view.when_label = backups_view.when_label = fixed
    home.backup_stat = functools.partial(home.backup_stat, now=NOW)
    app_module._fit_scale = lambda window: (
        None
    )  # siempre a 100 %, en cualquier pantalla
    app_module.tray.create = lambda: None  # sin icono en el área de notificación
    app_module._prepare_windows()
    from atril.gui import style

    style.register_fonts()
    original = tk.Tk.__init__

    def at_100(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.tk.call("tk", "scaling", 96 / 72)

    tk.Tk.__init__ = at_100
    window = app_module.App(load_station(root))
    window.overrideredirect(True)  # sin marco: cabe entera en pantallas de 1024 px
    window.geometry("+0+0")
    window.attributes("-topmost", True)
    return window


# --- 3. capturas ---------------------------------------------------------------------

PLAN = (
    ("inicio", "Inicio"),
    ("temarios", "Temarios"),
    ("biblioteca", "Biblioteca"),
    ("backups", "Backups"),
    ("actividad", "Actividad"),
    ("ajustes-atril", "Ajustes"),
)
"""Cada captura y su apartado, en el orden de :data:`SHOTS`."""


def _rows(table) -> bool:
    return bool(table.get_children())


def _ready(window, view: str) -> bool:
    """El apartado muestra ya sus datos (no el estado inicial vacío)."""
    views = window.views
    match view:
        case "Inicio":
            home = views["Inicio"]
            return home._headline.cget("text") != "Comprobando…" and bool(
                home._shown_stats
            )
        case "Temarios":
            return _rows(views["Temarios"]._kbs)
        case "Biblioteca" | "Backups":
            return _rows(views[view]._table)
        case "Actividad":
            return _rows(views["Actividad"]._list)
    return True


def _prepare_view(window, view: str) -> None:
    """Ajustes previos de algunas capturas, una vez cargado el apartado."""
    match view:
        case (
            "Biblioteca"
        ):  # ordenada por base, para que se vean las cuatro KB de Física
            window.views["Biblioteca"]._sorter.sort(1)
        case "Actividad":  # con el detalle de la operación más reciente
            table = window.views["Actividad"]._list
            table.selection_set(table.get_children()[0])
        case "Ajustes":
            window.views["Ajustes"].show_tab("Atril")


def capture(window, out: Path) -> None:
    """Captura cada apartado de :data:`PLAN` en ``out`` y cierra la ventana.

    Sin ``mainloop``: el script procesa los eventos de Tk mientras espera, así que
    cualquier error (también en un callback de Tk o en el trabajo de segundo plano)
    llega aquí, para la secuencia y sale como :class:`CaptureError`.
    """
    errors: list[BaseException] = []
    window.report_callback_exception = lambda _type, exc, _tb: errors.append(exc)
    submit = window.worker.submit

    def watched(task, on_done, on_error):
        def failed(exc: Exception) -> None:
            errors.append(exc)
            on_error(exc)

        return submit(task, on_done, failed)

    window.worker.submit = watched
    try:
        for name, view in PLAN:
            window.geometry("+0+0")  # Windows la abre desplazada y la pantalla la corta
            window.show_view(view)
            _wait(window, errors, f"«{view}»", lambda v=view: _ready(window, v))
            _prepare_view(window, view)
            _wait(window, errors, f"«{view}» preparado", lambda: True)
            _save(_grab(window), out / f"{name}.png", name)
    finally:
        window.destroy()


def _wait(window, errors: list[BaseException], what: str, ready: Callable[[], bool]):
    """Procesa eventos hasta que ``ready`` y la ventana estén quietos, o falla.

    Quieta: sin trabajo en segundo plano ni tareas de Tk pendientes durante
    varias vueltas seguidas (la última carga puede lanzar otra lectura).
    """
    deadline = time.monotonic() + TIMEOUT
    calm = 0
    while calm < 5:
        window.update()
        if errors:
            raise CaptureError(f"Error en la ventana durante {what}: {errors[0]!r}")
        if time.monotonic() > deadline:
            raise CaptureError(f"{what} no ha terminado de cargar en {TIMEOUT:.0f} s.")
        busy = window.worker.running or not ready()
        calm = 0 if busy else calm + 1
        time.sleep(0.1)


def _save(image, target: Path, name: str) -> None:
    """Guarda la captura si está entera."""
    if image.size != SIZE or _unpainted(image):
        raise CaptureError(
            f"Captura «{name}» incompleta ({image.size}, se esperaba {SIZE})."
        )
    image.save(target, optimize=True)


def _grab(window):
    """Imagen de la ventana tal como la pinta ella misma.

    En Windows usa ``PrintWindow``: no depende del tamaño de la pantalla (la del
    runner de GitHub recortaba la ventana). En Linux, una captura de la pantalla X.
    """
    from PIL import ImageGrab

    if sys.platform == "win32":
        return _print_window(int(window.wm_frame(), 16))
    x, y = window.winfo_rootx(), window.winfo_rooty()
    box = (x, y, x + window.winfo_width(), y + window.winfo_height())
    return ImageGrab.grab(bbox=box, xdisplay=os.environ["DISPLAY"])


def _print_window(hwnd: int):
    """``PrintWindow`` a un bitmap en memoria, liberando siempre cada recurso GDI.

    El bitmap se deselecciona (se restaura el objeto anterior del contexto) antes
    de leerlo con ``GetDIBits`` y de borrarlo, como exige la API de Windows.
    """
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetDIBits.argtypes = (
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    )
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise CaptureError("GetWindowRect ha fallado.")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(None)
    if not screen:
        raise CaptureError("GetDC ha fallado.")
    try:
        memory = gdi32.CreateCompatibleDC(screen)
        if not memory:
            raise CaptureError("CreateCompatibleDC ha fallado.")
        try:
            bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
            if not bitmap:
                raise CaptureError("CreateCompatibleBitmap ha fallado.")
            try:
                previous = gdi32.SelectObject(memory, bitmap)
                if not previous:
                    raise CaptureError("SelectObject ha fallado.")
                try:
                    if not user32.PrintWindow(hwnd, memory, 2):  # PW_RENDERFULLCONTENT
                        raise CaptureError(
                            "PrintWindow no ha podido pintar la ventana."
                        )
                finally:
                    gdi32.SelectObject(memory, previous)
                # BITMAPINFOHEADER: 32 bits, de arriba abajo, sin comprimir.
                header = (ctypes.c_uint32 * 10)(40, width, -height, 1 | (32 << 16), 0)
                pixels = ctypes.create_string_buffer(width * height * 4)
                if (
                    gdi32.GetDIBits(memory, bitmap, 0, height, pixels, header, 0)
                    != height
                ):
                    raise CaptureError("GetDIBits no ha leído la imagen entera.")
                return Image.frombuffer(
                    "RGB", (width, height), pixels, "raw", "BGRX", 0, 1
                )
            finally:
                gdi32.DeleteObject(bitmap)
        finally:
            gdi32.DeleteDC(memory)
    finally:
        user32.ReleaseDC(None, screen)


def _unpainted(image) -> bool:
    """La esquina inferior derecha es negra: parte de la ventana no se pintó."""
    corner = image.crop((image.width - 8, image.height - 8, image.width, image.height))
    return corner.convert("L").getextrema()[1] < 16


# --- 4. comprobación -----------------------------------------------------------------


def check_version() -> None:
    """La ventana es la versión que se documenta (la de ``pyproject.toml``)."""
    import atril

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = project["project"]["version"]
    if atril.__version__ != expected:
        raise CaptureError(
            f"La ventana es la versión {atril.__version__}, no la {expected} que se "
            "documenta."
        )


def validate(folder: Path) -> None:
    """Todas las capturas de :data:`SHOTS`, PNG válidos del tamaño y peso esperados."""
    from PIL import Image

    found = {path.name for path in folder.iterdir()}
    expected = {f"{name}.png" for name in SHOTS}
    if found != expected:
        raise CaptureError(
            f"Capturas inesperadas: faltan {sorted(expected - found)}, "
            f"sobran {sorted(found - expected)}."
        )
    for name in sorted(expected):
        path = folder / name
        if path.stat().st_size < MIN_BYTES:
            raise CaptureError(
                f"{name} ocupa demasiado poco ({path.stat().st_size} B)."
            )
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != SIZE:
                raise CaptureError(f"{name}: {image.format} de {image.size}.")


def publish(folder: Path, out: Path) -> None:
    """Sustituye las capturas de ``out`` por las de ``folder`` (ya validadas)."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    for new in folder.iterdir():
        shutil.copy2(new, out / new.name)
    validate(out)


def main() -> int:
    """Prepara la estación, captura, valida y publica; 1 si algo falla."""
    if len(sys.argv) != 2:
        print("Uso: capturas.py <carpeta>", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    try:
        check_version()
        with workspace() as (root, copies, work):
            prepare(root, copies, work)
            shots = work / "capturas"
            shots.mkdir()
            capture(open_window(root), shots)
            validate(shots)
            publish(shots, out)
    except CaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"{len(SHOTS)} capturas en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
