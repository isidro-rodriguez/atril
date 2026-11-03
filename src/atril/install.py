"""Instalación y actualización de DeepTutor en ``app/`` (sustituye a ``instalar.ps1``).

Todos los pasos son re-ejecutables: reutilizan lo que ya existe y vuelven a
aplicar la configuración de ``atril.toml``. Los comandos externos (git, uv, npm,
ollama, deeptutor) pasan por :func:`run_command` y :func:`capture`, que los tests
sustituyen.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from acodo.utils import get_file_hash

from atril import ollama
from atril.checks import Finding, error, info, ok, warning
from atril.config.station import Station

REQUIRED_TOOLS = ("git", "uv", "node", "npm")
"""Herramientas sin las que no se puede instalar."""

OPTIONAL_TOOLS = ("ollama", "claude")
"""Herramientas recomendadas: sin ellas DeepTutor arranca, pero sin RAG o sin LLM."""

NODE_MAJOR = 22
"""Versión mayor de Node.js que pide la guía de DeepTutor."""

DOCLING_PACKAGES = (
    "docling[xbrl]>=2.123.1",
    # Sin el extra format-video: exige compilar webrtcvad en Windows.
    "docling-slim[format-iwork,format-opendocument]>=2.123.1",
)
"""Paquetes del parser Docling."""

NPM_CI = (
    "ci",
    "--legacy-peer-deps",
    "--no-audit",
    "--no-fund",
    "--registry=https://registry.npmjs.org/",
    # El lockfile de DeepTutor apunta a registry.npmmirror.com.
    "--replace-registry-host=registry.npmmirror.com",
)
"""Argumentos de ``npm`` para instalar el frontend."""

_SETTINGS_SCRIPT = """
import json, sys
from deeptutor.services.config.runtime_settings import get_runtime_settings_service
want = json.loads(sys.argv[1])
service = get_runtime_settings_service()
li = service.load_llamaindex(include_process_overrides=False)
before = {"chunk_size": li.get("chunk_size"), "chunk_overlap": li.get("chunk_overlap")}
li.update(chunk_size=want["chunk_size"], chunk_overlap=want["chunk_overlap"])
service.save_llamaindex(li)
dp = service.load_document_parsing(include_process_overrides=False)
before["parser"] = dp.get("engine")
dp["engine"] = want["parser"]
engines = dict(dp.get("engines") or {})
for name in ("docling", "mineru"):
    if name in engines:
        engines[name] = {
            **engines[name], "allow_local_model_download": want["download_models"]
        }
dp["engines"] = engines
service.save_document_parsing(dp)
from deeptutor.services.config import get_model_catalog_service
def throttle(catalog):
    embedding = catalog["services"]["embedding"]
    for profile in embedding.get("profiles", []):
        if profile.get("id") == embedding.get("active_profile_id"):
            profile["batch_size"] = want["batch_size"]
            profile["batch_delay"] = want["batch_delay"]
get_model_catalog_service().update(throttle)
print(json.dumps(before))
"""
"""Ajustes de DeepTutor que ``config apply`` no cubre.

Parser, chunks y el ritmo del embedding (lote y pausa del perfil activo, que
``config apply`` reescribe). Se ejecuta con el Python de ``app/`` porque usa la
API interna de DeepTutor.

Se ejecuta con el Python de ``app/`` porque usa la API interna de DeepTutor.
"""


TESTED_DEEPTUTOR = ("1.7",)
"""Versiones (mayor.menor) de DeepTutor con las que se ha probado atril."""

_VERSION_FILE = "deeptutor/__version__.py"
"""Fichero de ``app/`` con la versión de DeepTutor."""


class StepError(Exception):
    """Un paso de la instalación ha fallado; el mensaje está en español."""


def run_command(
    command: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Ejecuta ``command`` mostrando su salida y devuelve el código de salida."""
    return subprocess.run(
        list(command), cwd=cwd, env=dict(env) if env else None, check=False
    ).returncode


def capture(
    command: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    *,
    check: bool = True,
) -> str:
    """Ejecuta ``command`` y devuelve su salida estándar.

    Args:
        command: Comando y argumentos.
        cwd: Carpeta de trabajo.
        env: Entorno; por defecto, el actual.
        check: Si es ``False``, devuelve la salida aunque el código no sea 0
            (``deeptutor doctor`` sale con 1 cuando falla algún check).

    Raises:
        StepError: Si el comando no existe o, con ``check``, termina con error.
    """
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(env) if env else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise StepError(f"no se puede ejecutar {command[0]}: {exc}.") from exc
    if check and result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = next((line for line in reversed(lines) if line.strip("{}[] ")), "")
        raise StepError(f"'{' '.join(command)}' ha fallado: {detail}")
    return result.stdout


def tool(name: str) -> str:
    """Ruta completa de una herramienta del ``PATH`` (``npm.cmd`` en Windows).

    Raises:
        StepError: Si no está instalada.
    """
    path = shutil.which(name)
    if path is None:
        raise StepError(f"no se encuentra '{name}' en el PATH.")
    return path


def check_tools() -> list[Finding]:
    """Herramientas necesarias y recomendadas, con la versión de Node.js."""
    findings = []
    for name in REQUIRED_TOOLS:
        path = shutil.which(name)
        findings.append(ok(f"{name}: {path}") if path else error(f"Falta {name}."))
    for name in OPTIONAL_TOOLS:
        path = shutil.which(name)
        findings.append(
            ok(f"{name}: {path}")
            if path
            else warning(f"Falta {name}: DeepTutor funcionará con limitaciones.")
        )
    if node := shutil.which("node"):
        try:
            version = capture([node, "--version"]).strip()
        except StepError:
            version = ""
        if version and not version.startswith(f"v{NODE_MAJOR}."):
            findings.append(
                warning(f"Node.js {version}; DeepTutor pide la {NODE_MAJOR} LTS.")
            )
    return findings


def setup_payload(station: Station) -> dict[str, Any]:
    """JSON para ``deeptutor config apply`` a partir de ``atril.toml``."""
    dt, embed = station.deeptutor, station.ollama
    payload: dict[str, Any] = {
        "embedding": {
            "provider": "ollama",
            "model": embed.embedding,
            "base_url": f"{embed.url.rstrip('/')}/api/embed",
            "dimension": embed.dimension,
        },
        "system": {"backend_port": dt.backend_port, "frontend_port": dt.frontend_port},
    }
    if dt.llm:
        payload["llm"] = {"provider": dt.llm.provider, "model": dt.llm.model}
    if dt.search:
        payload["search"] = {"provider": dt.search}
    return payload


def same_remote(first: str, second: str) -> bool:
    """Dos URL de git apuntan al mismo repo (https, ssh, con o sin ``.git``).

    Examples:
        >>> same_remote("git@github.com:HKUDS/DeepTutor.git",
        ...             "https://github.com/HKUDS/DeepTutor")
        True
    """
    return _remote_key(first) == _remote_key(second)


def _remote_key(url: str) -> str:
    """Forma comparable de una URL de git: ``host/ruta`` en minúsculas."""
    text = url.strip().rstrip("/").removesuffix(".git").lower()
    text = re.sub(r"^[a-z+]+://", "", text)
    text = re.sub(r"^[^@/]+@", "", text)
    return re.sub(r"^([^/:]+):(?!\d)", r"\1/", text)


def deeptutor_version(app_dir: Path) -> str | None:
    """Versión de DeepTutor del checkout (``None`` si no se encuentra)."""
    path = app_dir / _VERSION_FILE
    if not path.is_file():
        return None
    match = re.search(
        r"__version__\s*=\s*[\"']([^\"']+)", path.read_text(encoding="utf-8")
    )
    return match.group(1) if match else None


def version_finding(app_dir: Path) -> Finding:
    """Avisa si la versión de DeepTutor no es una de las probadas con atril."""
    version = deeptutor_version(app_dir)
    if version is None:
        return warning(f"No se encuentra la versión de DeepTutor ({_VERSION_FILE}).")
    if version.startswith(tuple(f"{tested}." for tested in TESTED_DEEPTUTOR)):
        return ok(f"DeepTutor {version}.")
    return warning(
        f"DeepTutor {version}: atril está probado con "
        f"{', '.join(TESTED_DEEPTUTOR)}; revisa el diagnóstico y los parches."
    )


def doctor_findings(report: Mapping[str, Any]) -> list[Finding]:
    """Convierte el JSON de ``deeptutor doctor --format json`` en comprobaciones."""
    findings = []
    for check in report.get("checks", []):
        label = (
            f"{check.get('label', check.get('key', '?'))}: {check.get('detail', '')}"
        )
        match check.get("status"):
            case "pass":
                findings.append(ok(label))
            case "skip":
                findings.append(info(label))
            case _:
                level = error if check.get("required") else warning
                findings.append(level(label))
    return findings


class Installer:
    """Pasos de instalación y actualización de una estación."""

    def __init__(self, station: Station, env: Mapping[str, str] | None = None) -> None:
        """Prepara los pasos; ``env`` es el entorno para ``deeptutor`` y su Python."""
        self.station = station
        self.app = station.app_dir
        self.env = dict(env) if env is not None else dict(os.environ)

    # --- código ------------------------------------------------------------

    @property
    def cloned(self) -> bool:
        """``True`` si ``app/`` ya es un checkout de git."""
        return (self.app / ".git").is_dir()

    def clone(self) -> Finding:
        """Clona la rama configurada (superficial) si ``app/`` no existe."""
        if self.cloned:
            return info(f"Código ya presente en {self.app}; no se cambia de rama.")
        if self.app.exists() and any(self.app.iterdir()):
            raise StepError(f"{self.app} existe y no es un checkout de git.")
        git = tool("git")
        dt = self.station.deeptutor
        command = [git, "-c", "core.longpaths=true", "clone", "--depth", "1"]
        self._run(
            [*command, "--branch", dt.branch, dt.repo, str(self.app)], "git clone"
        )
        self._run([git, "-C", str(self.app), "config", "core.longpaths", "true"], "git")
        return ok(f"Clonado {dt.repo} (rama {dt.branch}).")

    def head(self) -> str:
        """Commit actual de ``app/`` (hash corto y asunto)."""
        return capture(
            [tool("git"), "-C", str(self.app), "log", "-1", "--format=%h %s"]
        )

    def update_checkout(self) -> tuple[str, str]:
        """Trae la última versión de la rama y deja ``app/`` en ella.

        El checkout es superficial, así que no se hace merge: se descarga la punta
        de la rama y se mueve ``HEAD`` a ella. Antes se exige un árbol limpio (los
        parches deben estar deshechos).

        Returns:
            Commit anterior y nuevo (hash corto y asunto).

        Raises:
            StepError: Si hay cambios locales o git falla.
        """
        git = tool("git")
        self._check_origin(git)
        dirty = capture([git, "-C", str(self.app), "status", "--porcelain"]).strip()
        if dirty:
            files = ", ".join(line[3:] for line in dirty.splitlines()[:5])
            raise StepError(f"app/ tiene cambios locales ({files}); revísalos antes.")
        before = self.head().strip()
        branch = self.station.deeptutor.branch
        self._run(
            [git, "-C", str(self.app), "fetch", "--depth", "1", "origin", branch],
            "git fetch",
        )
        self._run(
            [git, "-C", str(self.app), "reset", "--hard", "FETCH_HEAD"], "git reset"
        )
        return before, self.head().strip()

    def _check_origin(self, git: str) -> None:
        """Exige que ``app/`` siga el repo y la rama de ``atril.toml``.

        ``reset --hard`` dejaría ``app/`` en otra rama o en otro repo sin avisar.
        """
        dt = self.station.deeptutor
        app = str(self.app)
        origin = capture([git, "-C", app, "remote", "get-url", "origin"]).strip()
        if not same_remote(origin, dt.repo):
            raise StepError(
                f"app/ sigue {origin}, pero atril.toml dice {dt.repo}; "
                "corrige uno de los dos antes de actualizar."
            )
        branch = capture([git, "-C", app, "branch", "--show-current"]).strip()
        if branch != dt.branch:
            raise StepError(
                f"app/ está en la rama {branch or '(ninguna)'!r}, pero atril.toml "
                f"dice {dt.branch!r}; cámbiala a mano antes de actualizar."
            )

    # --- Python ------------------------------------------------------------

    def venv_version(self) -> str | None:
        """Versión ``mayor.menor`` del Python de ``app/.venv`` (``None`` si falta)."""
        if not self.station.venv_python.is_file():
            return None
        try:
            output = capture(
                [
                    str(self.station.venv_python),
                    "-c",
                    "import sys; print('%d.%d' % sys.version_info[:2])",
                ]
            )
        except StepError:
            return None
        return output.strip() or None

    def venv_matches(self) -> bool:
        """``app/.venv`` existe con la versión de Python de ``atril.toml``."""
        current = self.venv_version()
        return current is not None and _same_python(
            current, self.station.deeptutor.python
        )

    def python_env(self, *, docling: bool) -> list[Finding]:
        """Crea ``app/.venv`` si falta e instala DeepTutor y los paquetes extra.

        Si el entorno existe con otra versión de Python que la de
        ``atril.toml``, se recrea (``uv venv --clear``).
        """
        uv = tool("uv")
        python = str(self.station.venv_python)
        findings = []
        version = self.station.deeptutor.python
        current = self.venv_version()
        if current is None or not _same_python(current, version):
            self._run(
                [uv, "venv", "--clear", "--seed", "--python", version, ".venv"],
                "uv venv",
                cwd=self.app,
            )
            if current is None:
                findings.append(ok(f"Entorno creado con Python {version}."))
            else:
                findings.append(
                    warning(
                        f"Entorno recreado: tenía Python {current}, pide {version}."
                    )
                )
        pip = [uv, "pip", "install", "--python", python]
        self._run(
            [*pip, "-r", "requirements/full.txt"], "requirements/full.txt", cwd=self.app
        )
        self._run(
            [*pip, "-e", ".", "--no-deps"], "instalación de DeepTutor", cwd=self.app
        )
        if packages := self.station.deeptutor.packages:
            self._run([*pip, *packages], "paquetes extra", cwd=self.app)
        findings.append(ok("Dependencias de Python instaladas."))

        if self.station.indexing.parser == "docling":
            if docling:
                self._run([*pip, *DOCLING_PACKAGES], "Docling", cwd=self.app)
                findings.append(ok("Parser Docling instalado."))
            else:
                findings.append(warning("Docling sin instalar (--sin-docling)."))
        return findings

    # --- frontend ----------------------------------------------------------

    @property
    def web_dir(self) -> Path:
        """Frontend de DeepTutor."""
        return self.app / "web"

    def frontend_lock_hash(self) -> str | None:
        """Hash de ``web/package-lock.json`` (``None`` si no existe)."""
        lock = self.web_dir / "package-lock.json"
        return get_file_hash(lock) if lock.is_file() else None

    def frontend(self, *, force: bool = False) -> Finding:
        """Instala ``web/node_modules`` si falta o si se fuerza."""
        if (self.web_dir / "node_modules").is_dir() and not force:
            return info("Frontend ya instalado.")
        self._run([tool("npm"), *NPM_CI], "npm ci", cwd=self.web_dir)
        return ok("Frontend instalado.")

    # --- Ollama ------------------------------------------------------------

    def embedding_model(self) -> Finding:
        """Descarga el modelo de embedding si Ollama responde y no lo tiene."""
        config = self.station.ollama
        status = ollama.get_status(config.url)
        if not status.running:
            return warning(f"Ollama no responde: descarga luego {config.embedding}.")
        if any(ollama.same_model(name, config.embedding) for name in status.installed):
            return ok(f"Modelo {config.embedding} ya descargado.")
        self._run([tool("ollama"), "pull", config.embedding], "ollama pull")
        return ok(f"Modelo {config.embedding} descargado.")

    # --- configuración de DeepTutor ---------------------------------------

    def configure(self) -> list[Finding]:
        """``deeptutor init`` y ``config apply`` con los datos de ``atril.toml``."""
        cli = str(self.station.deeptutor_cli)
        home = ("--home", str(self.station.root))
        self._run([cli, "init", *home, "--non-interactive"], "deeptutor init")
        with tempfile.TemporaryDirectory() as folder:
            setup = Path(folder) / "setup.json"
            setup.write_text(json.dumps(setup_payload(self.station)), encoding="utf-8")
            self._run(
                [cli, "config", "apply", str(setup), *home, "--check"], "config --check"
            )
            self._run([cli, "config", "apply", str(setup), *home], "config apply")
        return [ok("Ajustes de LLM, embedding, búsqueda y puertos aplicados.")]

    def runtime_settings(self) -> list[Finding]:
        """Aplica parser, chunks y descarga de modelos con el Python de ``app/``."""
        indexing = self.station.indexing
        want = {
            "parser": indexing.parser,
            "chunk_size": indexing.chunk_size,
            "chunk_overlap": indexing.chunk_overlap,
            "download_models": indexing.download_models,
            "batch_size": indexing.batch_size,
            "batch_delay": indexing.pause_ms / 1000,
        }
        output = capture(
            [str(self.station.venv_python), "-c", _SETTINGS_SCRIPT, json.dumps(want)],
            cwd=self.app,
            env=self.env,
        )
        try:
            before = json.loads(output.strip().splitlines()[-1])
        except (IndexError, ValueError) as exc:
            raise StepError(
                "los ajustes internos de DeepTutor no responden como se esperaba "
                "(¿ha cambiado su API?)."
            ) from exc
        findings = [
            ok(
                f"Parser {indexing.parser}; chunks {indexing.chunk_size}/"
                f"{indexing.chunk_overlap}; embedding en lotes de {indexing.batch_size}"
                + (
                    f" con pausa de {indexing.pause_ms} ms."
                    if indexing.pause_ms
                    else "."
                )
            )
        ]
        old_chunks = (before.get("chunk_size"), before.get("chunk_overlap"))
        if old_chunks != (indexing.chunk_size, indexing.chunk_overlap):
            findings.append(
                warning(
                    f"Chunks cambiados ({old_chunks[0]}/{old_chunks[1]} → "
                    f"{indexing.chunk_size}/{indexing.chunk_overlap}): las KB "
                    "existentes conservan los anteriores hasta reindexarlas."
                )
            )
        return findings

    def doctor(self) -> list[Finding]:
        """Diagnóstico (``doctor`` no admite ``--home``; usa el entorno)."""
        output = capture(
            [str(self.station.deeptutor_cli), "doctor", "--format", "json"],
            env=self.env,
            check=False,
        )
        start = output.find("{")
        try:
            report = json.loads(output[start:]) if start >= 0 else None
        except ValueError:
            report = None
        if not isinstance(report, dict) or not isinstance(report.get("checks"), list):
            raise StepError(
                "'deeptutor doctor --format json' no devuelve el formato esperado; "
                "puede que DeepTutor haya cambiado (ejecútalo a mano para verlo)."
            )
        return doctor_findings(report)

    # --- interno -----------------------------------------------------------

    def _run(self, command: Sequence[str], what: str, cwd: Path | None = None) -> None:
        """Ejecuta un paso; falla con :class:`StepError` si termina con error."""
        code = run_command(command, cwd=cwd, env=self.env)
        if code != 0:
            raise StepError(f"{what} ha fallado (código {code}).")


def _same_python(current: str, wanted: str) -> bool:
    """``current`` (``3.13``) cumple la versión pedida (``3.13`` o ``3.13.5``)."""
    return wanted == current or wanted.startswith(f"{current}.")
