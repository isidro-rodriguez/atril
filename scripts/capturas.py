r"""Capturas de la web desde la ventana real de atril, con una estación de ejemplo.

Uso (desde la raíz del repositorio)::

    uv run --with pillow python scripts/capturas.py [carpeta]

Por defecto escribe en ``docs/assets/images/capturas/`` (no se versionan: las
genera la CI de la web en cada construcción). Tres pasos separados:

1. :func:`prepare` crea la estación de ejemplo: una alumna de 2.º de
   Bachillerato de Ciencias con un temario por asignatura, copias, verificaciones
   y actividad, todo con fechas fijas para que las capturas sean reproducibles.
2. :func:`open_window` abre la ventana real con los servicios simulados
   (DeepTutor, Ollama y herramientas en marcha, sin buscar actualizaciones).
3. :func:`capture` recorre los apartados y guarda cada uno en PNG.

En Windows usa ``D:\Estudio`` (estación) y ``D:\Copias\Atril`` (copias), las
rutas que se ven en la web. Para no pisar datos reales, se niega a usarlas si
ya existen sin la marca que deja este script. En otros sistemas usa una carpeta
temporal (solo para revisar el aspecto durante el desarrollo).
"""

import datetime as dt
import functools
import hashlib
import json
import os
import shutil
import sys
import tempfile
import tkinter as tk
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "images" / "capturas"
MARK = ".atril-capturas"
"""Marca de las carpetas creadas por este script (las únicas que borra)."""

NOW = dt.datetime(2026, 11, 9, 18, 30)
"""Momento fijo de las capturas: fechas y «Hoy/Ayer» no cambian entre ejecuciones."""

SHOTS = ("inicio", "temarios", "biblioteca", "backups", "actividad", "ajustes-atril")
"""Ficheros que genera (y que la web usa)."""

SUBJECTS = {
    "Física": [
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
        "Problemas resueltos PAU 2024",
        "Problemas resueltos PAU 2025",
    ],
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


def folders() -> tuple[Path, Path]:
    """Estación y destino de las copias."""
    if sys.platform == "win32":
        return Path(r"D:\Estudio"), Path(r"D:\Copias\Atril")
    base = Path(tempfile.gettempdir()) / "atril-capturas"
    return base / "Estudio", base / "Copias" / "Atril"


def _fresh(folder: Path) -> None:
    """Vacía ``folder`` si la creó este script; si no, se niega."""
    if folder.exists():
        if not (folder / MARK).exists():
            raise SystemExit(f"{folder} ya existe y no es de este script: no se toca.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / MARK).write_text("Carpeta de scripts/capturas.py\n", encoding="utf-8")


def prepare() -> Path:
    """Crea la estación de ejemplo y devuelve su raíz."""
    from atril.config import load_station, load_syllabus
    from atril.config.station import init_station
    from atril.ops import syllabus as syllabus_ops

    root, copies = folders()
    _fresh(root)
    _fresh(copies)
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

    downloads = root.parent / "atril-capturas-pdf"
    shutil.rmtree(downloads, ignore_errors=True)
    downloads.mkdir()
    for index, (name, documents) in enumerate(SUBJECTS.items()):
        syllabus = syllabus_ops.create(station, name)
        for document in documents:
            pdf = downloads / f"{document}.pdf"
            seed = hashlib.sha256(f"{name}/{document}".encode()).digest()
            pdf.write_bytes(b"%PDF-1.7 " + seed * 64)  # contenido fijo
            syllabus_ops.add_source(
                load_syllabus(syllabus.root), str(pdf), title=document
            )
        if name == "Física":
            syllabus_ops.add_source(
                load_syllabus(syllabus.root),
                "https://www.boe.es/buscar/pdf/2022/BOE-A-2022-6008-consolidado.pdf",
                title="Real Decreto 243/2022 (currículo de Bachillerato)",
            )
        _index(
            station,
            load_syllabus(syllabus.root),
            index,
            skip=2 if name == "Física" else 0,
        )
    shutil.rmtree(downloads)
    _backups(station, copies)
    _activity(station)
    (station.data_dir / "atril" / "ventana.json").write_text(
        json.dumps({"temario": "fisica"}), encoding="utf-8"
    )
    return root


def _index(station, syllabus, order: int, skip: int) -> None:
    """Marca como indexadas todas las fuentes salvo las ``skip`` últimas."""
    from atril.knowledge import IndexedSource, Ledger, content_digest, ledger_path

    ledger = Ledger(ledger_path(syllabus))
    for kb in syllabus.knowledge_bases:
        sources = syllabus.sources_of(kb)
        for source in sources[: len(sources) - skip]:
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


def capture(window, out: Path) -> list[Path]:
    """Recorre los apartados y guarda cada uno; devuelve los ficheros."""
    out.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    plan = [
        ("inicio", "Inicio", None),
        ("temarios", "Temarios", None),
        ("biblioteca", "Biblioteca", None),
        ("backups", "Backups", None),
        ("actividad", "Actividad", "primera"),
        ("ajustes-atril", "Ajustes", "Atril"),
    ]

    def settle() -> None:
        for _ in range(3):
            thread = window.worker._thread
            if thread is not None:
                thread.join(10)
            window.worker.poll()
            window.update()

    def shoot(name: str) -> None:
        window.geometry(
            "+0+0"
        )  # Windows la abre desplazada y la pantalla corta el resto
        settle()
        image = _grab(window)
        expected = (window.winfo_width(), window.winfo_height())
        if image.size != expected or _unpainted(image):
            raise SystemExit(
                f"Captura «{name}» incompleta ({image.size}, ventana {expected} en "
                f"{window.winfo_rootx()},{window.winfo_rooty()}, "
                f"pantalla {window.winfo_screenwidth()}x{window.winfo_screenheight()})."
            )
        target = out / f"{name}.png"
        image.save(target, optimize=True)
        saved.append(target)

    def step(index: int = 0) -> None:
        if index == len(plan):
            window.destroy()
            return
        name, view, extra = plan[index]
        window.show_view(view)
        settle()
        if extra == "primera":
            table = window.views["Actividad"]._list
            table.selection_set(table.get_children()[0])
        elif extra is not None:
            window.views["Ajustes"].show_tab(extra)
        window.after(700, lambda: (shoot(name), step(index + 1)))

    window.after(1200, step)
    window.mainloop()
    return saved


def _grab(window):
    """Imagen de la ventana tal como la pinta ella misma.

    En Windows usa ``PrintWindow``: no depende del tamaño de la pantalla (la del
    runner de GitHub recortaba la ventana). En Linux, una captura de la pantalla X.
    """
    from PIL import Image, ImageGrab

    width, height = window.winfo_width(), window.winfo_height()
    if sys.platform != "win32":
        x, y = window.winfo_rootx(), window.winfo_rooty()
        box = (x, y, x + width, y + height)
        return ImageGrab.grab(bbox=box, xdisplay=os.environ["DISPLAY"])
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = int(window.wm_frame(), 16)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    gdi32.SelectObject(memory, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory, 2):  # PW_RENDERFULLCONTENT
            raise SystemExit("PrintWindow no ha podido pintar la ventana.")
        header = (ctypes.c_uint32 * 10)(40, width, -height, 1 | (32 << 16), 0)
        pixels = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(memory, bitmap, 0, height, pixels, header, 0)
        return Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)


def _unpainted(image) -> bool:
    """La esquina inferior derecha es negra: parte de la ventana no se pintó."""
    corner = image.crop((image.width - 8, image.height - 8, image.width, image.height))
    return corner.convert("L").getextrema()[1] < 16


def check(saved: list[Path]) -> None:
    """Falla si falta una captura o la versión no es la de ``pyproject.toml``."""
    import atril

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = project["project"]["version"]
    if atril.__version__ != expected:
        raise SystemExit(
            f"La ventana es la versión {atril.__version__}, no la {expected} que se "
            "documenta: ejecuta uv sync."
        )
    missing = [name for name in SHOTS if not any(p.stem == name for p in saved)]
    if missing:
        raise SystemExit(f"Faltan capturas: {', '.join(missing)}.")


def main() -> None:
    """Prepara la estación, abre la ventana, captura y comprueba."""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    root = prepare()
    saved = capture(open_window(root), out)
    check(saved)
    print(f"{len(saved)} capturas en {out}")


if __name__ == "__main__":
    main()
