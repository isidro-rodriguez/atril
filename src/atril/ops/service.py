"""Servicio DeepTutor: arrancar, parar, estado y parches.

Solo se cierran procesos cuya línea de comandos tiene una ruta de la estación
(:meth:`atril.processes.PortOwner.belongs_to`); los ajenos se señalan y no se tocan.
Ollama está fuera de la estación: solo se cierra el que abrió atril
(:func:`ollama_owner`).
"""

import json
import time

from atril import backup, ollama, processes
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

    Abre Ollama si hace falta, cierra restos de un arranque anterior de la
    estación y aplica los parches pendientes (con DeepTutor parado es seguro: así
    no se pierden si algo los deshizo, como una actualización a medias). Se niega
    si los puertos son de otro programa.

    Raises:
        AtrilError: Si no arranca; lleva el final del log del lanzador.
    """
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
    reporter.show(apply_pending_patches(dt.station))

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


def open_url(station: Station, reporter: Reporter, timeout: int = 600) -> str:
    """Arranca DeepTutor si no responde y devuelve la URL para el navegador.

    Raises:
        AtrilError: Si no está instalado o no arranca.
    """
    dt = installed(station)
    if not dt.ready():
        start(dt, reporter, timeout)
    return dt.frontend_url


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
        sections.append(("Ollama", _ollama_findings(station)))
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
            warning(
                f"Procesos huérfanos: {pids(orphans.own)}. Se cierran al parar "
                "DeepTutor."
            )
        )
    return findings


def patch_finding(name: str, state: PatchState) -> Finding:
    """Comprobación de un parche según su estado."""
    match state:
        case PatchState.APPLIED:
            return ok(f"{name}: aplicado.")
        case PatchState.PENDING:
            return warning(
                f"{name}: pendiente. Aplica los parches con DeepTutor parado."
            )
        case PatchState.CHANGED:
            return error(
                f"{name}: el código de DeepTutor ha cambiado; revisa el parche."
            )
        case PatchState.NO_FILE:
            return error(f"{name}: no existe {PATCHES[name].file} en app/.")


def apply_pending_patches(station: Station) -> list[Finding]:
    """Aplica los parches pendientes y dice el estado de cada uno.

    Solo toca los pendientes (texto original intacto): un parche cuyo código ha
    cambiado se queda como está y se informa como error.
    """
    findings = []
    for name in station.deeptutor.patches:
        patch = PATCHES[name]
        before = patch.state(station.app_dir)
        after = patch.apply(station.app_dir)
        if before is PatchState.PENDING and after is PatchState.APPLIED:
            findings.append(ok(f"{name}: aplicado ahora."))
        else:
            findings.append(patch_finding(name, after))
    return findings


def patch_findings(station: Station) -> list[Finding]:
    """Estado de los parches configurados."""
    return [
        patch_finding(name, PATCHES[name].state(station.app_dir))
        for name in station.deeptutor.patches
    ]


def ensure_ollama(station: Station, reporter: Reporter) -> list[Finding]:
    """Abre Ollama si no responde y devuelve sus comprobaciones."""
    config = station.ollama
    if config is None:
        return []
    current = ollama.get_status(config.url)
    if not current.running and ollama.is_installed():
        start_ollama(station, reporter)
        current = ollama.get_status(config.url)
    findings = ollama.check(current, config)
    if not current.running:
        findings.append(warning("Sin Ollama, el RAG no funcionará."))
    return findings


def ollama_url(station: Station) -> str:
    """Dirección de Ollama: la de ``[ollama]`` o la de por defecto."""
    return station.ollama.url if station.ollama else ollama.DEFAULT_URL


def start_ollama(station: Station, reporter: Reporter) -> None:
    """Abre Ollama, recuerda que lo arrancó atril y espera a que responda.

    Raises:
        AtrilError: Si no está instalado o no responde a tiempo.
    """
    pid = ollama.launch()
    if pid is None:
        raise AtrilError("Ollama no está instalado.")
    started = processes.started_at(pid)
    state = station.ollama_state_file
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"pid": pid, "inicio": started}), encoding="utf-8")
    url = ollama_url(station)
    deadline = time.monotonic() + OLLAMA_START_TIMEOUT
    with reporter.busy("Abriendo Ollama..."):
        while not ollama.get_status(url).running:
            if time.monotonic() > deadline:
                raise AtrilError(
                    f"Ollama no responde tras {OLLAMA_START_TIMEOUT:.0f} s."
                )
            time.sleep(1)


def ollama_owner(station: Station) -> int | None:
    """PID del Ollama que arrancó atril, si sigue siendo ese proceso.

    Se compara también la hora de arranque: Windows reutiliza los PID, y un
    Ollama abierto por el usuario (o por otro programa) nunca se toca.
    """
    try:
        data = json.loads(station.ollama_state_file.read_text(encoding="utf-8"))
        pid, started = int(data["pid"]), data["inicio"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if started is None or processes.started_at(pid) != started:
        return None
    return pid


def stop_ollama(station: Station, reporter: Reporter) -> None:
    """Cierra el Ollama que arrancó atril (y solo ese).

    Raises:
        AtrilError: Si Ollama no lo arrancó atril.
    """
    pid = ollama_owner(station)
    if pid is None:
        raise AtrilError("este Ollama no lo abrió atril; ciérralo desde su icono.")
    with reporter.busy("Cerrando Ollama..."):
        processes.kill_tree(pid)
    station.ollama_state_file.unlink(missing_ok=True)


def _ollama_findings(station: Station) -> list[Finding]:
    """Estado de Ollama; sin ``[ollama]`` es opcional y solo se informa."""
    if station.ollama is None:
        return [info("Sin [ollama]: DeepTutor funciona, pero no se indexan fuentes.")]
    return ollama.check(ollama.get_status(station.ollama.url), station.ollama)


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


def shutdown(station: Station, reporter: Reporter) -> None:
    """Para DeepTutor (lo arrancara quien lo arrancara) y el Ollama de atril.

    Es la salida desde el área de notificación. Un Ollama abierto aparte no se
    toca (ver :func:`ollama_owner`).

    Raises:
        AtrilError: Si DeepTutor sigue respondiendo tras pararlo.
    """
    dt = DeepTutor(station)
    if dt.installed:
        stop(dt, reporter)
    if ollama_owner(station) is not None:
        stop_ollama(station, reporter)
