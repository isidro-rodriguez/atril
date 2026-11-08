"""Comandos de control de DeepTutor: arrancar, parar, estado y parches.

La lógica está en :mod:`atril.ops.service`; aquí solo se traducen las opciones y
se muestra el resultado.
"""

import webbrowser
from typing import Annotated

import typer

from atril.checks import Finding, ok
from atril.commands._common import (
    console,
    fail,
    fail_error,
    get_station,
    reporter,
    show,
    success,
)
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.ops import service
from atril.ops.service import patch_finding as patch_finding
from atril.patches import PATCHES, PatchState


def start(
    ctx: typer.Context,
    no_browser: Annotated[
        bool, typer.Option("--sin-navegador", help="No abre el navegador al terminar.")
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--espera",
            min=10,
            help="Segundos de espera; tras actualizar compila el frontend.",
        ),
    ] = 600,
) -> None:
    """Arranca DeepTutor (y Ollama si hace falta) y abre el navegador."""
    dt = _installed(ctx)
    if dt.ready():
        console.print(f"DeepTutor ya está en marcha: [link]{dt.frontend_url}[/]")
    else:
        launch(dt, timeout)
    if not no_browser:
        webbrowser.open(dt.frontend_url)


def stop(ctx: typer.Context) -> None:
    """Detiene DeepTutor y cierra sus procesos huérfanos."""
    shutdown(_installed(ctx))


def launch(dt: DeepTutor, timeout: int) -> None:
    """Arranca DeepTutor y espera a que responda; termina con error si no lo hace."""
    try:
        service.start(dt, reporter, timeout)
    except AtrilError as exc:
        fail_error(exc)
    success(f"Listo: {dt.frontend_url}")


def shutdown(dt: DeepTutor) -> None:
    """Detiene DeepTutor y sus huérfanos; termina con error si no se liberan."""
    try:
        service.stop(dt, reporter)
    except AtrilError as exc:
        fail_error(exc)
    success("DeepTutor detenido.")


def status(ctx: typer.Context) -> None:
    """Muestra DeepTutor, parches, Ollama, espacio libre y la última copia."""
    clean = True
    for title, findings in service.status(get_station(ctx), reporter):
        clean = show(findings, title) and clean
    if not clean:
        raise typer.Exit(1)


def patches(
    ctx: typer.Context,
    check_only: Annotated[
        bool, typer.Option("--comprobar", help="Solo muestra el estado; no modifica.")
    ] = False,
) -> None:
    """Aplica los parches de atril.toml sobre app/ (idempotente)."""
    station = get_station(ctx)
    if not station.deeptutor.patches:
        console.print("atril.toml no declara parches.")
        return

    findings: list[Finding] = []
    changed = False
    for name in station.deeptutor.patches:
        patch = PATCHES[name]
        before = patch.state(station.app_dir)
        after = before if check_only else patch.apply(station.app_dir)
        if before is PatchState.PENDING and after is PatchState.APPLIED:
            changed = True
            findings.append(ok(f"{name}: aplicado ahora."))
        else:
            findings.append(patch_finding(name, after))
    clean = show(findings)
    if changed:
        console.print(
            "[yellow]Reinicia DeepTutor para que los cambios surtan efecto.[/]"
        )
    if not clean:
        raise typer.Exit(1)


def _installed(ctx: typer.Context) -> DeepTutor:
    """DeepTutor de la estación; termina con error si no está instalado."""
    try:
        return service.installed(get_station(ctx))
    except AtrilError as exc:
        fail(str(exc))
