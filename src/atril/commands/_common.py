"""Utilidades compartidas por los comandos: estación, consola Rich y errores.

Toda la salida pasa por :data:`console` (y :data:`err_console` para errores). El
texto que viene de fuera (rutas, mensajes de configuración con ``[[fuente]]``,
líneas de comandos) se escapa para que Rich no lo interprete como markup.
"""

import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NoReturn

import typer
from acodo.utils import valid_slug
from rich.console import Console
from rich.markup import escape

from atril.checks import Finding, Level, info, ok, warning
from atril.config import (
    ConfigError,
    Station,
    Syllabus,
    load_station,
    load_syllabi,
    load_syllabus,
)
from atril.config.station import STATION_FILE, init_station
from atril.config.syllabus import KnowledgeBase

console = Console(soft_wrap=True)
"""Consola de salida normal; ``soft_wrap`` evita cortar rutas y mensajes largos."""

err_console = Console(stderr=True, soft_wrap=True)
"""Consola de errores."""

_STYLE = {
    Level.OK: ("✓", "green"),
    Level.INFO: ("·", "dim"),
    Level.WARNING: ("!", "yellow"),
    Level.ERROR: ("✗", "bold red"),
}


def fail(message: str) -> NoReturn:
    """Muestra ``message`` como error y termina con código 1."""
    err_console.print(f"[bold red]Error:[/] {escape(message)}")
    raise typer.Exit(1)


STATION_VARIABLE = "ATRIL_ESTACION"
"""Variable de usuario con la raíz de la única estación del equipo."""


def station_root(ctx: typer.Context) -> Path:
    """Raíz de la estación guardada; en la primera ejecución, la configura."""
    if ctx.obj is not None:
        return ctx.obj
    root = saved_station()
    if root is None or not (root / STATION_FILE).is_file():
        if not _interactive():
            fail(
                f"no hay estación configurada ({STATION_VARIABLE}); ejecuta atril "
                "una vez en un terminal para indicarla."
            )
        root = _first_run()
    ctx.obj = root  # el resto del comando no vuelve a leerla
    return root


def saved_station() -> Path | None:
    """Estación guardada: del entorno o, en Windows, del registro del usuario.

    ``setx`` no cambia el entorno de los terminales ya abiertos; por eso, si
    falta en el entorno, se lee del registro.
    """
    value = os.environ.get(STATION_VARIABLE)
    if not value and sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, STATION_VARIABLE)
        except OSError:
            value = None
    return Path(str(value)) if value else None


def _interactive() -> bool:
    """Hay alguien al teclado (no un script ni una tarea programada)."""
    return sys.stdin.isatty()


def _first_run() -> Path:
    """Elige la estación (la carpeta actual u otra) o la inicializa, y la guarda."""
    console.print("[bold]Primera ejecución de atril:[/] falta indicar la estación.")
    cwd = Path.cwd()
    if (cwd / STATION_FILE).is_file() and _yes(
        f"¿Usar {cwd} como estación de atril?", default=True
    ):
        return _save(cwd)
    answer = typer.prompt("Carpeta de la estación")
    root = Path(answer.strip().strip('"')).expanduser().resolve()
    if (root / STATION_FILE).is_file():
        if _yes(f"¿Usar {root} como estación de atril?", default=True):
            return _save(root)
    elif _yes(f"No hay {STATION_FILE} en {root}. ¿Inicializar ahí la estación?"):
        init_station(root)
        show([info(f"Creado {root / STATION_FILE}: revísalo y ejecuta atril validar.")])
        return _save(root)
    fail("no se ha configurado ninguna estación.")


def _yes(question: str, *, default: bool = False) -> bool:
    """Pregunta sí/no en español (s/sí/n/no; Intro = valor por defecto)."""
    hint = "S/n" if default else "s/N"
    while True:
        answer = typer.prompt(f"{question} [{hint}]", default="", show_default=False)
        answer = answer.strip().lower()
        if not answer:
            return default
        if answer in {"s", "si", "sí", "y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        err_console.print("Responde s o n.")


def _save(root: Path) -> Path:
    """Guarda la estación como variable de usuario y la usa ya en este proceso."""
    os.environ[STATION_VARIABLE] = str(root)
    show([persist_station(root)])
    return root


def persist_station(root: Path) -> Finding:
    """Guarda ``ATRIL_ESTACION`` en el entorno del usuario.

    En Windows usa ``setx`` (registro del usuario, sin ficheros propios de
    atril). En otros sistemas, indica la línea para el perfil de la shell.
    """
    if os.name != "nt":
        return info(f"Añade a tu perfil de shell: export {STATION_VARIABLE}={root}")
    result = subprocess.run(
        ["setx", STATION_VARIABLE, str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return warning(
            f"No se ha podido guardar {STATION_VARIABLE}; hazlo con: "
            f'setx {STATION_VARIABLE} "{root}"'
        )
    return ok(
        f"Estación guardada: {root} (para cambiarla: setx {STATION_VARIABLE} ...)."
    )


def get_station(ctx: typer.Context) -> Station:
    """Carga ``atril.toml``; termina con error si falta o no es válido."""
    try:
        return load_station(station_root(ctx))
    except ConfigError as exc:
        fail(str(exc))


def get_syllabus(ctx: typer.Context, syllabus_id: str) -> Syllabus:
    """Carga un temario por id; termina con error si no existe o no es válido."""
    station = get_station(ctx)
    if not valid_slug(syllabus_id):
        fail(
            f"id de temario no válido: {syllabus_id!r} (minúsculas, cifras y guiones)."
        )
    root = station.syllabi_dir / syllabus_id
    if not (root / "temario.toml").is_file():
        found = sorted(
            p.parent.name for p in station.syllabi_dir.glob("*/temario.toml")
        )
        names = ", ".join(found) or "ninguno"
        fail(f"no existe el temario {syllabus_id!r} (disponibles: {names}).")
    try:
        return load_syllabus(root)
    except ConfigError as exc:
        fail(str(exc))


def find_kb(ctx: typer.Context, kb_id: str) -> tuple[Syllabus, KnowledgeBase]:
    """Temario y KB a partir del id de KB (único en la estación)."""
    station = get_station(ctx)
    try:
        syllabi, _ = load_syllabi(station.syllabi_dir)
    except ConfigError as exc:
        fail(str(exc))
    for syllabus in syllabi:
        for kb in syllabus.knowledge_bases:
            if kb.id == kb_id:
                return syllabus, kb
    known = ", ".join(kb.id for s in syllabi for kb in s.knowledge_bases) or "ninguna"
    fail(f"no existe la KB {kb_id!r} en ningún temario (disponibles: {known}).")


def load_or_fail[T](factory: Callable[[], T]) -> T:
    """Ejecuta ``factory``; un fichero de estado o de configuración dañado termina."""
    try:
        return factory()
    except ConfigError as exc:
        fail(str(exc))


def show(findings: Iterable[Finding], title: str | None = None) -> bool:
    """Muestra las comprobaciones, una por línea, con símbolo y color por nivel.

    Args:
        findings: Comprobaciones, en el orden en que se muestran.
        title: Título de la sección, si lo hay.

    Returns:
        ``True`` si ninguna es un error.
    """
    if title:
        console.rule(f"[bold]{escape(title)}[/]", align="left")
    clean = True
    for finding in findings:
        symbol, style = _STYLE[finding.level]
        console.print(f"  [{style}]{symbol}[/] {escape(finding.message)}")
        clean = clean and finding.level is not Level.ERROR
    return clean


def success(message: str) -> None:
    """Mensaje final de éxito."""
    console.print(f"[bold green]{escape(message)}[/]")
