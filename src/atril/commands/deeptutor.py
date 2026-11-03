"""Comandos de control de DeepTutor: arrancar, parar, estado y parches."""

import time
import webbrowser
from typing import Annotated

import typer

from atril import ollama
from atril.checks import Finding, error, info, ok, warning
from atril.commands._common import fail, get_station, show, title
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.patches import PATCHES, PatchState
from atril.processes import PortOwner

OLLAMA_START_TIMEOUT = 30.0
"""Segundos que se espera a que la aplicación de Ollama responda."""


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
            help="Segundos máximos de espera (tras actualizar, compila el frontend).",
        ),
    ] = 600,
) -> None:
    """Arranca DeepTutor (y Ollama si hace falta) y abre el navegador."""
    station = get_station(ctx)
    dt = _installed(station)

    if dt.ready():
        typer.echo(f"DeepTutor ya está en marcha: {dt.frontend_url}")
        _open(dt, no_browser)
        return

    show(_patch_findings(station))
    show(_ensure_ollama(station))

    orphans = dt.orphans()
    if orphans.foreign:
        show(_foreign_findings(orphans.foreign))
        fail("los puertos de DeepTutor están ocupados por otro programa.")
    if orphans.own:
        show(
            [warning(f"Cerrando restos de un arranque anterior: {_pids(orphans.own)}.")]
        )
        dt.kill(orphans.own)

    typer.echo("Arrancando DeepTutor...")
    if dt.start() != 0:
        _fail_with_log(dt, "'deeptutor start' ha terminado con error.")
    if not dt.wait(dt.ready, timeout, on_tick=lambda: typer.echo(".", nl=False)):
        typer.echo()
        _fail_with_log(dt, f"DeepTutor no responde tras {timeout} s.")
    typer.echo()
    typer.secho(f"Listo: {dt.frontend_url}", fg=typer.colors.GREEN)
    _open(dt, no_browser)


def stop(ctx: typer.Context) -> None:
    """Detiene DeepTutor y cierra sus procesos huérfanos."""
    station = get_station(ctx)
    dt = _installed(station)

    typer.echo("Deteniendo DeepTutor...")
    if dt.stop() != 0:
        show([warning("'deeptutor stop' ha terminado con error; se sigue.")])
    time.sleep(2)

    orphans = dt.orphans()
    if orphans.own:
        show([info(f"Cerrando huérfanos: {_pids(orphans.own)}.")])
        dt.kill(orphans.own)
    if orphans.foreign:
        show(_foreign_findings(orphans.foreign))

    if dt.wait(lambda: not dt.backend_up() and not dt.frontend_up(), timeout=10):
        typer.secho("DeepTutor detenido.", fg=typer.colors.GREEN)
    else:
        fail("algo sigue respondiendo en los puertos de DeepTutor.")


def status(ctx: typer.Context) -> None:
    """Muestra el estado de DeepTutor, sus parches y Ollama."""
    station = get_station(ctx)
    dt = DeepTutor(station)

    title("DeepTutor")
    clean = show(_service_findings(dt))
    if station.deeptutor.patches:
        title("Parches")
        clean = show(_patch_findings(station)) and clean
    title("Ollama")
    clean = (
        show(ollama.check(ollama.get_status(station.ollama.url), station.ollama))
        and clean
    )
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
        typer.echo("atril.toml no declara parches.")
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
            findings.append(_patch_finding(name, after))
    clean = show(findings)
    if changed:
        typer.echo("Reinicia DeepTutor para que los cambios surtan efecto.")
    if not clean:
        raise typer.Exit(1)


def _installed(station: Station) -> DeepTutor:
    """DeepTutor de la estación; termina con error si no está instalado."""
    dt = DeepTutor(station)
    if not dt.installed:
        fail(f"no se encuentra {station.deeptutor_cli}; instala DeepTutor en app/.")
    return dt


def _open(dt: DeepTutor, no_browser: bool) -> None:
    """Abre el frontend en el navegador salvo que se pida lo contrario."""
    if not no_browser:
        webbrowser.open(dt.frontend_url)


def _fail_with_log(dt: DeepTutor, message: str) -> None:
    """Muestra el final del log del lanzador y termina con error."""
    lines = dt.launcher_log_tail()
    if lines:
        typer.echo(f"--- últimas líneas de {dt.station.launcher_log} ---")
        typer.echo("\n".join(lines))
    fail(message)


def _pids(owners: tuple[PortOwner, ...]) -> str:
    """Lista ``nombre (PID n)`` sin repetir procesos."""
    seen = {owner.pid: owner.name or "?" for owner in owners}
    return ", ".join(f"{name} (PID {pid})" for pid, name in seen.items())


def _foreign_findings(owners: tuple[PortOwner, ...]) -> list[Finding]:
    """Avisos de procesos ajenos en los puertos de DeepTutor."""
    return [
        warning(
            f"Puerto {owner.port} ocupado por {owner.name or '?'} (PID {owner.pid}), "
            f"que no es de esta estación; no se toca. {owner.cmdline}".rstrip()
        )
        for owner in owners
    ]


def _service_findings(dt: DeepTutor) -> list[Finding]:
    """Instalación, servicios en marcha y ocupación de puertos."""
    if not dt.installed:
        return [error(f"No instalado: falta {dt.station.deeptutor_cli}.")]
    findings = [ok(f"Instalado en {dt.station.app_dir}.")]
    backend, frontend = dt.backend_up(), dt.frontend_up()
    if backend and frontend:
        findings.append(ok(f"En marcha: {dt.frontend_url}"))
    elif not backend and not frontend:
        findings.append(info("Parado."))
    else:
        parts = (
            "backend" if backend else "frontend",
            "frontend" if backend else "backend",
        )
        findings.append(
            warning(f"Arranque incompleto: responde el {parts[0]}, no el {parts[1]}.")
        )
    orphans = dt.orphans()
    if orphans.foreign:
        findings.extend(_foreign_findings(orphans.foreign))
    if orphans.own and not (backend and frontend):
        findings.append(
            warning(f"Procesos huérfanos: {_pids(orphans.own)} (atril parar).")
        )
    return findings


def _patch_finding(name: str, state: PatchState) -> Finding:
    """Comprobación de un parche según su estado."""
    match state:
        case PatchState.APPLIED:
            return ok(f"{name}: aplicado.")
        case PatchState.PENDING:
            return warning(f"{name}: pendiente (atril parches).")
        case PatchState.CHANGED:
            return error(
                f"{name}: el código de DeepTutor ha cambiado; revisa el parche."
            )
        case PatchState.NO_FILE:
            return error(f"{name}: no existe {PATCHES[name].file} en app/.")


def _patch_findings(station: Station) -> list[Finding]:
    """Estado de los parches configurados."""
    return [
        _patch_finding(name, PATCHES[name].state(station.app_dir))
        for name in station.deeptutor.patches
    ]


def _ensure_ollama(station: Station) -> list[Finding]:
    """Abre Ollama si no responde y devuelve sus comprobaciones."""
    config = station.ollama
    current = ollama.get_status(config.url)
    if not current.running and (app := ollama.app_path()):
        typer.echo("Abriendo Ollama...")
        ollama.launch_app(app)
        deadline = time.monotonic() + OLLAMA_START_TIMEOUT
        while not current.running and time.monotonic() < deadline:
            time.sleep(2)
            current = ollama.get_status(config.url)
    findings = ollama.check(current, config)
    if not current.running:
        findings.append(warning("Sin Ollama, el RAG no funcionará."))
    return findings
