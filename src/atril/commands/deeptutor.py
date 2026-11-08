"""Comandos de control de DeepTutor: arrancar, parar, estado y parches."""

import time
import webbrowser
from typing import Annotated

import typer
from rich.markup import escape
from rich.panel import Panel

from atril import backup, ollama
from atril.checks import Finding, error, info, ok, warning
from atril.commands._common import console, fail, get_station, show, success
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
            help="Segundos de espera; tras actualizar compila el frontend.",
        ),
    ] = 600,
) -> None:
    """Arranca DeepTutor (y Ollama si hace falta) y abre el navegador."""
    station = get_station(ctx)
    dt = _installed(station)
    if dt.ready():
        console.print(f"DeepTutor ya está en marcha: [link]{dt.frontend_url}[/]")
    else:
        launch(dt, timeout)
    if not no_browser:
        webbrowser.open(dt.frontend_url)


def stop(ctx: typer.Context) -> None:
    """Detiene DeepTutor y cierra sus procesos huérfanos."""
    shutdown(_installed(get_station(ctx)))


def launch(dt: DeepTutor, timeout: int) -> None:
    """Arranca DeepTutor y espera a que responda; termina con error si no lo hace.

    Abre Ollama si hace falta, avisa de parches pendientes y cierra restos de un
    arranque anterior de la estación. Se niega si los puertos son de otro programa.
    """
    show(_patch_findings(dt.station))
    show(_ensure_ollama(dt.station))

    orphans = dt.orphans()
    if orphans.foreign:
        show(_foreign_findings(orphans.foreign))
        fail("los puertos de DeepTutor están ocupados por otro programa.")
    if orphans.own:
        show(
            [warning(f"Cerrando restos de un arranque anterior: {_pids(orphans.own)}.")]
        )
        dt.kill(orphans.own)

    with console.status("Arrancando DeepTutor..."):
        started = dt.start() == 0
    if not started:
        _fail_with_log(dt, "'deeptutor start' ha terminado con error.")
    with console.status(
        "Esperando a backend y frontend (tras actualizar, compila el frontend)..."
    ):
        # Se deja de esperar si el lanzador muere (p. ej. falla el build del frontend).
        ready = dt.wait(lambda: dt.ready() or dt.launcher_alive() is False, timeout)
    if not dt.ready():
        if ready:
            _fail_with_log(dt, "el lanzador de DeepTutor ha terminado sin arrancar.")
        _fail_with_log(dt, f"DeepTutor no responde tras {timeout} s.")
    success(f"Listo: {dt.frontend_url}")


def shutdown(dt: DeepTutor) -> None:
    """Detiene DeepTutor y sus huérfanos; termina con error si no se liberan."""
    idle = (
        dt.launcher_alive() is not True and not dt.backend_up() and not dt.frontend_up()
    )
    if idle:
        show([info("No hay lanzador de DeepTutor en marcha.")])
    else:
        with console.status("Deteniendo DeepTutor..."):
            stopped = dt.stop() == 0
        if not stopped:
            show([warning("'deeptutor stop' ha terminado con error; se sigue.")])
        time.sleep(2)

    orphans = dt.orphans()
    if orphans.own:
        show([info(f"Cerrando huérfanos: {_pids(orphans.own)}.")])
        dt.kill(orphans.own)
    if orphans.foreign:
        show(_foreign_findings(orphans.foreign))

    with console.status("Comprobando que los puertos quedan libres..."):
        down = dt.wait(lambda: not dt.backend_up() and not dt.frontend_up(), timeout=10)
    if down:
        success("DeepTutor detenido.")
    else:
        fail("algo sigue respondiendo en los puertos de DeepTutor.")


def status(ctx: typer.Context) -> None:
    """Muestra DeepTutor, parches, Ollama, espacio libre y la última copia."""
    station = get_station(ctx)
    dt = DeepTutor(station)

    with console.status("Consultando DeepTutor y Ollama..."):
        service = _service_findings(dt)
        ollama_findings = ollama.check(
            ollama.get_status(station.ollama.url), station.ollama
        )
    clean = show(service, "DeepTutor")
    if station.deeptutor.patches:
        clean = show(_patch_findings(station), "Parches") and clean
    clean = show(ollama_findings, "Ollama") and clean
    clean = show(backup.station_findings(station), "Estación y copias") and clean
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


def _installed(station: Station) -> DeepTutor:
    """DeepTutor de la estación; termina con error si no está instalado."""
    dt = DeepTutor(station)
    if not dt.installed:
        fail(f"no se encuentra {station.deeptutor_cli}; instala DeepTutor en app/.")
    return dt


def _fail_with_log(dt: DeepTutor, message: str) -> None:
    """Muestra el final del log del lanzador y termina con error."""
    lines = dt.launcher_log_tail()
    if lines:
        console.print(
            Panel(
                escape("\n".join(lines)),
                title=escape(str(dt.station.launcher_log)),
                title_align="left",
                border_style="red",
            )
        )
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


def patch_finding(name: str, state: PatchState) -> Finding:
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
        patch_finding(name, PATCHES[name].state(station.app_dir))
        for name in station.deeptutor.patches
    ]


def _ensure_ollama(station: Station) -> list[Finding]:
    """Abre Ollama si no responde y devuelve sus comprobaciones."""
    config = station.ollama
    current = ollama.get_status(config.url)
    if not current.running and (app := ollama.app_path()):
        ollama.launch_app(app)
        deadline = time.monotonic() + OLLAMA_START_TIMEOUT
        with console.status("Abriendo Ollama..."):
            while not current.running and time.monotonic() < deadline:
                time.sleep(2)
                current = ollama.get_status(config.url)
    findings = ollama.check(current, config)
    if not current.running:
        findings.append(warning("Sin Ollama, el RAG no funcionará."))
    return findings
