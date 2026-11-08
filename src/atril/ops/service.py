"""Servicio DeepTutor: arrancar, parar, estado y parches.

Solo se cierran procesos cuya línea de comandos tiene una ruta de la estación
(:meth:`atril.processes.PortOwner.belongs_to`); los ajenos se señalan y no se tocan.
"""

import time

from atril import backup, ollama
from atril.checks import Finding, error, info, ok, warning
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.ops import Reporter
from atril.patches import PATCHES, PatchState
from atril.processes import PortOwner

OLLAMA_START_TIMEOUT = 30.0
"""Segundos que se espera a que la aplicación de Ollama responda."""

Section = tuple[str, list[Finding]]
"""Título y comprobaciones de una parte del estado."""


def installed(station: Station) -> DeepTutor:
    """DeepTutor de la estación.

    Raises:
        AtrilError: Si no está instalado.
    """
    dt = DeepTutor(station)
    if not dt.installed:
        raise AtrilError(
            f"no se encuentra {station.deeptutor_cli}; instala DeepTutor en app/."
        )
    return dt


def start(dt: DeepTutor, reporter: Reporter, timeout: int) -> None:
    """Arranca DeepTutor y espera a que responda.

    Abre Ollama si hace falta, avisa de parches pendientes y cierra restos de un
    arranque anterior de la estación. Se niega si los puertos son de otro programa.

    Raises:
        AtrilError: Si no arranca; lleva el final del log del lanzador.
    """
    reporter.show(patch_findings(dt.station))
    reporter.show(ensure_ollama(dt.station, reporter))

    orphans = dt.orphans()
    if orphans.foreign:
        reporter.show(foreign_findings(orphans.foreign))
        raise AtrilError("los puertos de DeepTutor están ocupados por otro programa.")
    if orphans.own:
        reporter.show(
            [warning(f"Cerrando restos de un arranque anterior: {pids(orphans.own)}.")]
        )
        dt.kill(orphans.own)

    with reporter.busy("Arrancando DeepTutor..."):
        started = dt.start() == 0
    if not started:
        raise _with_log(dt, "'deeptutor start' ha terminado con error.")
    with reporter.busy(
        "Esperando a backend y frontend (tras actualizar, compila el frontend)..."
    ):
        # Se deja de esperar si el lanzador muere (p. ej. falla el build del frontend).
        ready = dt.wait(lambda: dt.ready() or dt.launcher_alive() is False, timeout)
    if not dt.ready():
        if ready:
            raise _with_log(dt, "el lanzador de DeepTutor ha terminado sin arrancar.")
        raise _with_log(dt, f"DeepTutor no responde tras {timeout} s.")


def stop(dt: DeepTutor, reporter: Reporter) -> None:
    """Detiene DeepTutor y sus huérfanos.

    Raises:
        AtrilError: Si algo sigue respondiendo en sus puertos.
    """
    idle = (
        dt.launcher_alive() is not True and not dt.backend_up() and not dt.frontend_up()
    )
    if idle:
        reporter.show([info("No hay lanzador de DeepTutor en marcha.")])
    else:
        with reporter.busy("Deteniendo DeepTutor..."):
            stopped = dt.stop() == 0
        if not stopped:
            reporter.show(
                [warning("'deeptutor stop' ha terminado con error; se sigue.")]
            )
        time.sleep(2)

    orphans = dt.orphans()
    if orphans.own:
        reporter.show([info(f"Cerrando huérfanos: {pids(orphans.own)}.")])
        dt.kill(orphans.own)
    if orphans.foreign:
        reporter.show(foreign_findings(orphans.foreign))

    with reporter.busy("Comprobando que los puertos quedan libres..."):
        down = dt.wait(lambda: not dt.backend_up() and not dt.frontend_up(), timeout=10)
    if not down:
        raise AtrilError("algo sigue respondiendo en los puertos de DeepTutor.")


def status(station: Station, reporter: Reporter) -> list[Section]:
    """Estado de DeepTutor, parches, Ollama, espacio libre y la última copia."""
    dt = DeepTutor(station)
    with reporter.busy("Consultando DeepTutor y Ollama..."):
        sections: list[Section] = [("DeepTutor", service_findings(dt))]
        if station.deeptutor.patches:
            sections.append(("Parches", patch_findings(station)))
        current = ollama.get_status(station.ollama.url)
        sections.append(("Ollama", ollama.check(current, station.ollama)))
    sections.append(("Estación y copias", backup.station_findings(station)))
    return sections


def service_findings(dt: DeepTutor) -> list[Finding]:
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
        findings.extend(foreign_findings(orphans.foreign))
    if orphans.own and not (backend and frontend):
        findings.append(
            warning(f"Procesos huérfanos: {pids(orphans.own)} (atril parar).")
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


def patch_findings(station: Station) -> list[Finding]:
    """Estado de los parches configurados."""
    return [
        patch_finding(name, PATCHES[name].state(station.app_dir))
        for name in station.deeptutor.patches
    ]


def ensure_ollama(station: Station, reporter: Reporter) -> list[Finding]:
    """Abre Ollama si no responde y devuelve sus comprobaciones."""
    config = station.ollama
    current = ollama.get_status(config.url)
    if not current.running and (app := ollama.app_path()):
        ollama.launch_app(app)
        deadline = time.monotonic() + OLLAMA_START_TIMEOUT
        with reporter.busy("Abriendo Ollama..."):
            while not current.running and time.monotonic() < deadline:
                time.sleep(2)
                current = ollama.get_status(config.url)
    findings = ollama.check(current, config)
    if not current.running:
        findings.append(warning("Sin Ollama, el RAG no funcionará."))
    return findings


def pids(owners: tuple[PortOwner, ...]) -> str:
    """Lista ``nombre (PID n)`` sin repetir procesos."""
    seen = {owner.pid: owner.name or "?" for owner in owners}
    return ", ".join(f"{name} (PID {pid})" for pid, name in seen.items())


def foreign_findings(owners: tuple[PortOwner, ...]) -> list[Finding]:
    """Avisos de procesos ajenos en los puertos de DeepTutor."""
    return [
        warning(
            f"Puerto {owner.port} ocupado por {owner.name or '?'} (PID {owner.pid}), "
            f"que no es de esta estación; no se toca. {owner.cmdline}".rstrip()
        )
        for owner in owners
    ]


def _with_log(dt: DeepTutor, message: str) -> AtrilError:
    """Error con el final del log del lanzador."""
    return AtrilError(
        message, log=dt.launcher_log_tail(), log_title=str(dt.station.launcher_log)
    )
