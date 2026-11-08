"""Mantenimiento de DeepTutor: instalar, actualizar, parches y diagnóstico.

Cada paso del :class:`~atril.install.Installer` se anuncia como espera y su
resultado se muestra con su título; un paso que falla lanza
:class:`~atril.install.StepError`, que es un :class:`~atril.errors.AtrilError`.
"""

import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from atril import install
from atril.checks import Finding, Level, info, ok
from atril.config import Syllabus, load_syllabi
from atril.config.station import Station
from atril.deeptutor import DeepTutor
from atril.errors import AtrilError
from atril.install import Installer
from atril.lock import station_lock
from atril.ops import Reporter, service
from atril.ops.service import patch_finding
from atril.ops.station import refresh_path
from atril.patches import PATCHES, PatchState
from atril.processes import no_window

RESTART_TIMEOUT = 900
"""Segundos de espera al volver a arrancar DeepTutor tras actualizar."""

WINGET_IDS = {
    "git": "Git.Git",
    "uv": "astral-sh.uv",
    "node": "OpenJS.NodeJS.LTS",
    "npm": "OpenJS.NodeJS.LTS",
    "ollama": "Ollama.Ollama",
}
"""Paquete de ``winget`` que instala cada herramienta."""


@dataclass(frozen=True, slots=True)
class Updated:
    """Resultado de una actualización de DeepTutor."""

    before: str
    after: str
    """Commit (hash y asunto) antes y después."""

    @property
    def changed(self) -> bool:
        """El código ha cambiado."""
        return self.before != self.after

    @property
    def previous(self) -> str:
        """Hash completo del commit anterior, para volver atrás."""
        return self.before.split(" ", 1)[0]


def install_deeptutor(
    station: Station, reporter: Reporter, *, docling: bool = True
) -> None:
    """Instala DeepTutor en ``app/`` o completa la instalación (re-ejecutable).

    Clona la rama configurada, crea el entorno de Python, instala el frontend,
    descarga el modelo de embedding, aplica la configuración de ``atril.toml`` y
    los parches, y termina con el diagnóstico de DeepTutor.

    Raises:
        AtrilError: Si DeepTutor está en marcha, faltan herramientas o un paso falla.
    """
    with station_lock(station, "instalación de DeepTutor"):
        dt = DeepTutor(station)
        if dt.backend_up() or dt.frontend_up():
            raise AtrilError("DeepTutor está en marcha; páralo antes de instalar.")
        installer = Installer(station, dt.env())
        tools = install.check_tools()
        reporter.show(tools, "Herramientas")
        if _has_errors(tools):
            raise AtrilError(
                "instala las herramientas que faltan y vuelve a intentarlo."
            )
        _step(reporter, "Código", installer.clone)
        reporter.show([install.version_finding(station.app_dir)])
        _step(reporter, "Python", lambda: installer.python_env(docling=docling))
        _step(reporter, "Frontend", installer.frontend)
        _step(reporter, "Modelo de embedding", installer.embedding_model)
        _step(reporter, "Configuración de DeepTutor", installer.configure)
        _step(reporter, "Parser y chunks", installer.runtime_settings)
        patches = apply_patches(station)
        reporter.show(patches, "Parches")
        report = _step(reporter, "Diagnóstico", installer.doctor)
        if _has_errors(patches) or _has_errors(report):
            raise AtrilError(
                "la instalación ha terminado con errores; revisa los puntos marcados."
            )


def update_deeptutor(
    station: Station,
    reporter: Reporter,
    *,
    docling: bool = True,
    restart: bool = True,
    commit: str | None = None,
) -> Updated:
    """Actualiza DeepTutor a la punta de su rama (o a ``commit``) y reaplica todo.

    Para DeepTutor si está en marcha, deshace los parches, trae el código,
    reinstala dependencias (el frontend solo si cambia su lockfile), reaplica la
    configuración y los parches, pasa el diagnóstico y lo vuelve a arrancar.

    Raises:
        AtrilError: Si no está instalado, un parche ya no encaja o un paso falla.
    """
    with station_lock(station, "actualización de DeepTutor"):
        dt = DeepTutor(station)
        installer = Installer(station, dt.env())
        if not installer.cloned or not dt.installed:
            raise AtrilError("DeepTutor no está instalado; instálalo antes.")
        was_running = dt.backend_up() or dt.frontend_up()
        if was_running:
            service.stop(dt, reporter)

        reporter.show(revert_patches(station), "Deshacer parches")
        lock_before = installer.frontend_lock_hash()
        with reporter.busy("Trayendo el código..."):
            result = Updated(*installer.update_checkout(commit))
        if result.changed:
            code = [
                ok(f"{result.before} → {result.after}"),
                info(f"Para volver a la anterior: commit {result.previous}"),
            ]
        else:
            code = [info(f"Sin cambios: {result.before}")]
        reporter.show(code, "Código")
        reporter.show([install.version_finding(station.app_dir)])
        if result.changed or not installer.venv_matches():
            _step(reporter, "Python", lambda: installer.python_env(docling=docling))
        if result.changed:
            force = installer.frontend_lock_hash() != lock_before
            _step(reporter, "Frontend", lambda: installer.frontend(force=force))
        _step(reporter, "Configuración de DeepTutor", installer.configure)
        _step(reporter, "Parser y chunks", installer.runtime_settings)

        patches = apply_patches(station)
        reporter.show(patches, "Parches")
        if _has_errors(patches):
            raise AtrilError(
                "algún parche ya no encaja con el código nuevo; revísalo antes de "
                "arrancar."
            )
        if _has_errors(_step(reporter, "Diagnóstico", installer.doctor)):
            raise AtrilError("DeepTutor actualizado con errores; revisa lo marcado.")
        if was_running and restart:
            service.start(dt, reporter, RESTART_TIMEOUT)
        return result


def doctor(station: Station, reporter: Reporter) -> list[Finding]:
    """Diagnóstico de DeepTutor (``deeptutor doctor``)."""
    dt = service.installed(station)
    return _step(reporter, "Diagnóstico", Installer(station, dt.env()).doctor)


def validate(station: Station) -> tuple[list[Syllabus], list[str]]:
    """Valida ``atril.toml`` (ya cargado) y el ``temario.toml`` de cada temario."""
    return load_syllabi(station.syllabi_dir)


def patch(station: Station, *, check_only: bool = False) -> tuple[list[Finding], bool]:
    """Aplica (o solo comprueba) los parches de ``atril.toml``.

    Returns:
        Estado de cada parche y si alguno se ha aplicado ahora (hay que reiniciar).
    """
    findings: list[Finding] = []
    changed = False
    for name in station.deeptutor.patches:
        current = PATCHES[name]
        before = current.state(station.app_dir)
        after = before if check_only else current.apply(station.app_dir)
        if before is PatchState.PENDING and after is PatchState.APPLIED:
            changed = True
            findings.append(ok(f"{name}: aplicado ahora."))
        else:
            findings.append(patch_finding(name, after))
    return findings, changed


def apply_patches(station: Station) -> list[Finding]:
    """Aplica los parches configurados y devuelve su estado."""
    findings = []
    for name in station.deeptutor.patches:
        state = PATCHES[name].apply(station.app_dir)
        findings.append(patch_finding(name, state))
    return findings or [info("Sin parches configurados.")]


def revert_patches(station: Station) -> list[Finding]:
    """Deshace los parches para que git pueda actualizar el árbol limpio."""
    findings = []
    for name in station.deeptutor.patches:
        state = PATCHES[name].revert(station.app_dir)
        if state is PatchState.PENDING:
            findings.append(info(f"{name}: deshecho."))
        else:
            findings.append(patch_finding(name, state))
    return findings or [info("Sin parches configurados.")]


@dataclass(frozen=True, slots=True)
class Tool:
    """Herramienta externa: si está, dónde y si es imprescindible."""

    name: str
    path: str | None
    required: bool


def tools() -> list[Tool]:
    """Herramientas que usa atril (git, uv, Node.js...) y si están en el PATH."""
    return [
        Tool(name, shutil.which(name), name in install.REQUIRED_TOOLS)
        for name in (*install.REQUIRED_TOOLS, *install.OPTIONAL_TOOLS)
    ]


def missing_tools() -> list[str]:
    """Herramientas que ``winget`` sabe instalar y no están en el PATH."""
    return [name for name in WINGET_IDS if shutil.which(name) is None]


def install_tools(names: list[str], reporter: Reporter) -> list[Finding]:
    """Instala herramientas con ``winget`` (Windows) y recarga el PATH.

    ``winget`` puede pedir permiso de administrador para Git y Node.js.

    Raises:
        AtrilError: Fuera de Windows o si ``winget`` no está disponible.
    """
    winget = shutil.which("winget")
    if sys.platform != "win32" or winget is None:
        raise AtrilError(
            "la instalación automática usa winget (Windows 10/11); instala a mano: "
            + ", ".join(names)
        )
    findings = []
    for package in dict.fromkeys(WINGET_IDS[name] for name in names):
        with reporter.busy(f"Instalando {package} con winget..."):
            result = subprocess.run(
                [
                    winget,
                    "install",
                    "--id",
                    package,
                    "--exact",
                    "--silent",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=no_window(),
            )
        if result.returncode == 0:
            findings.append(ok(f"{package}: instalado."))
        else:
            last = (result.stdout + result.stderr).strip().splitlines()[-1:]
            detail = last[0] if last else f"código {result.returncode}"
            findings.append(Finding(Level.ERROR, f"{package}: {detail}"))
    refresh_path()
    return findings


def _step(
    reporter: Reporter,
    title: str,
    action: Callable[[], Finding] | Callable[[], list[Finding]],
) -> list[Finding]:
    """Ejecuta un paso con espera y muestra su resultado con su título."""
    with reporter.busy(f"{title}..."):
        result = action()
    findings: list[Finding] = result if isinstance(result, list) else [result]
    reporter.show(findings, title)
    return findings


def _has_errors(findings: list[Finding]) -> bool:
    """Alguna comprobación es un error."""
    return any(finding.level is Level.ERROR for finding in findings)
