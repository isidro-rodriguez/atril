"""Comandos de instalación: ``atril instalar`` y ``atril actualizar``."""

from collections.abc import Callable
from typing import Annotated

import typer
from rich.markup import escape

from atril import install
from atril.checks import Finding, info, ok
from atril.commands._common import console, fail, get_station, show, success
from atril.commands.deeptutor import launch, patch_finding, shutdown
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.install import Installer, StepError
from atril.patches import PATCHES, PatchState

NoDocling = Annotated[
    bool,
    typer.Option(
        "--sin-docling", help="No instala el parser Docling (descarga grande, PyTorch)."
    ),
]


def install_command(ctx: typer.Context, no_docling: NoDocling = False) -> None:
    """Instala DeepTutor en [bold]app/[/] o completa la instalación (re-ejecutable).

    Clona la rama configurada, crea el entorno de Python, instala el frontend,
    descarga el modelo de embedding, aplica la configuración de atril.toml y los
    parches, y termina con el diagnóstico de DeepTutor.
    """
    station = get_station(ctx)
    dt = DeepTutor(station)
    _require_stopped(dt)
    installer = Installer(station, dt.env())

    if not show(install.check_tools(), "Herramientas"):
        fail("instala las herramientas que faltan y vuelve a ejecutar.")
    _step("Código", installer.clone)
    _step("Python", lambda: installer.python_env(docling=not no_docling))
    _step("Frontend", installer.frontend)
    _step("Modelo de embedding", installer.embedding_model)
    _step("Configuración de DeepTutor", installer.configure)
    _step("Parser y chunks", installer.runtime_settings)
    patches_clean = show(_apply_patches(station), "Parches")
    doctor_clean = show(_step_value(installer.doctor), "Diagnóstico")
    if not (patches_clean and doctor_clean):
        fail("la instalación ha terminado con errores; revisa los puntos marcados.")
    success("DeepTutor instalado. Arráncalo con: atril arrancar")


def update_command(
    ctx: typer.Context,
    no_docling: NoDocling = False,
    no_restart: Annotated[
        bool,
        typer.Option(
            "--sin-arrancar", help="No vuelve a arrancar DeepTutor al terminar."
        ),
    ] = False,
) -> None:
    """Actualiza DeepTutor a la última versión de su rama y reaplica los parches.

    Para DeepTutor si está en marcha, deshace los parches, trae la rama, reinstala
    dependencias (el frontend solo si cambia su lockfile) y vuelve a aplicarlos.
    """
    station = get_station(ctx)
    dt = DeepTutor(station)
    installer = Installer(station, dt.env())
    if not installer.cloned or not dt.installed:
        fail("DeepTutor no está instalado; usa atril instalar.")

    was_running = dt.backend_up() or dt.frontend_up()
    if was_running:
        shutdown(dt)

    show(_revert_patches(station), "Deshacer parches")
    lock_before = installer.frontend_lock_hash()
    with console.status("Trayendo la última versión..."):
        before, after = _step_value(installer.update_checkout)
    if before == after:
        show([info(f"Ya estaba en la última versión: {before}")], "Código")
    else:
        show([ok(f"{before} → {after}")], "Código")
        _step("Python", lambda: installer.python_env(docling=not no_docling))
        lock_changed = installer.frontend_lock_hash() != lock_before
        _step("Frontend", lambda: installer.frontend(force=lock_changed))

    if not show(_apply_patches(station), "Parches"):
        fail(
            "algún parche ya no encaja con el código nuevo; revísalo antes de arrancar."
        )
    success("DeepTutor actualizado.")
    if was_running and not no_restart:
        launch(dt, timeout=900)


def _require_stopped(dt: DeepTutor) -> None:
    """Termina con error si DeepTutor está en marcha (Windows bloquea sus ficheros)."""
    if dt.backend_up() or dt.frontend_up():
        fail("DeepTutor está en marcha; páralo antes con: atril parar")


def _step(title: str, action: Callable[[], Finding | list[Finding]]) -> None:
    """Ejecuta un paso con su título y muestra su resultado; termina si falla."""
    console.rule(f"[bold]{escape(title)}[/]", align="left")
    result = _step_value(action)
    show(result if isinstance(result, list) else [result])


def _step_value[T](action: Callable[[], T]) -> T:
    """Ejecuta ``action`` convirtiendo :class:`StepError` en un error de la CLI."""
    try:
        return action()
    except StepError as exc:
        fail(str(exc))


def _apply_patches(station: Station) -> list[Finding]:
    """Aplica los parches configurados y devuelve su estado."""
    findings = []
    for name in station.deeptutor.patches:
        state = PATCHES[name].apply(station.app_dir)
        findings.append(patch_finding(name, state))
    return findings or [info("Sin parches configurados.")]


def _revert_patches(station: Station) -> list[Finding]:
    """Deshace los parches para que git pueda actualizar el árbol limpio."""
    findings = []
    for name in station.deeptutor.patches:
        state = PATCHES[name].revert(station.app_dir)
        if state is PatchState.PENDING:
            findings.append(info(f"{name}: deshecho."))
        else:
            findings.append(patch_finding(name, state))
    return findings or [info("Sin parches configurados.")]
