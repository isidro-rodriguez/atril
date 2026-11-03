"""Comprobación del servidor Ollama y del modelo de embedding.

Lecciones de la instalación previa que se comprueban aquí:

- Otro modelo cargado puede expulsar el de embedding de la VRAM y la recarga
  fallar (error CUDA): se avisa de los modelos ajenos cargados.
- ``OLLAMA_CONTEXT_LENGTH`` debe coincidir con ``[ollama] contexto``.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acodo.utils import parse_size

from atril import net
from atril.checks import Finding, error, info, ok, warning
from atril.config.station import OllamaConfig


@dataclass(frozen=True, slots=True)
class LoadedModel:
    """Modelo cargado en memoria (``/api/ps``)."""

    name: str
    size_vram: int
    context_length: int | None


@dataclass(frozen=True, slots=True)
class OllamaStatus:
    """Estado del servidor Ollama."""

    running: bool
    version: str | None = None
    installed: tuple[str, ...] = ()
    loaded: tuple[LoadedModel, ...] = ()


def get_status(url: str, timeout: float = 3.0) -> OllamaStatus:
    """Consulta versión, modelos instalados y modelos cargados.

    Args:
        url: URL base del servidor (``http://localhost:11434``).
        timeout: Segundos de espera por petición.

    Returns:
        El estado; ``running=False`` si el servidor no responde.
    """
    base = url.rstrip("/")
    try:
        version = net.get_json(f"{base}/api/version", timeout)
        tags = net.get_json(f"{base}/api/tags", timeout)
        ps = net.get_json(f"{base}/api/ps", timeout)
    except (OSError, ValueError):
        return OllamaStatus(running=False)
    return OllamaStatus(
        running=True,
        version=version.get("version"),
        installed=tuple(model["name"] for model in tags.get("models", [])),
        loaded=tuple(_loaded(model) for model in ps.get("models", [])),
    )


def _loaded(raw: dict[str, Any]) -> LoadedModel:
    """Entrada de ``/api/ps``."""
    return LoadedModel(
        name=raw["name"],
        size_vram=int(raw.get("size_vram", 0)),
        context_length=raw.get("context_length"),
    )


def same_model(a: str, b: str) -> bool:
    """Compara nombres de modelo; sin etiqueta equivale a ``:latest``.

    Examples:
        >>> same_model("nomic-embed-text", "nomic-embed-text:latest")
        True
        >>> same_model("qwen3-embedding:8b", "qwen3-embedding:4b")
        False
    """

    def normalize(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return normalize(a) == normalize(b)


def check(status: OllamaStatus, config: OllamaConfig) -> list[Finding]:
    """Evalúa el estado de Ollama frente a la configuración de la estación."""
    if not status.running:
        return [error(f"Ollama no responde en {config.url}.")]

    findings = [ok(f"Ollama {status.version or '?'} en {config.url}.")]
    if any(same_model(name, config.embedding) for name in status.installed):
        findings.append(ok(f"Modelo de embedding instalado: {config.embedding}."))
    else:
        findings.append(
            error(
                f"Falta el modelo de embedding {config.embedding} "
                f"(ollama pull {config.embedding})."
            )
        )

    for model in status.loaded:
        vram = parse_size(model.size_vram)
        if not same_model(model.name, config.embedding):
            findings.append(
                warning(
                    f"Modelo ajeno cargado: {model.name} ({vram} de VRAM); puede "
                    "expulsar al de embedding durante el indexado."
                )
            )
            continue
        findings.append(info(f"Embedding cargado ({vram} de VRAM)."))
        if model.context_length and model.context_length != config.context:
            findings.append(
                warning(
                    f"Contexto del embedding cargado: {model.context_length}; "
                    f"atril.toml espera {config.context} (OLLAMA_CONTEXT_LENGTH)."
                )
            )

    env_context = os.environ.get("OLLAMA_CONTEXT_LENGTH")
    if env_context and env_context != str(config.context):
        findings.append(
            warning(
                f"OLLAMA_CONTEXT_LENGTH={env_context} en el entorno, pero "
                f"atril.toml declara contexto = {config.context}."
            )
        )
    return findings


def probe_embedding(config: OllamaConfig, timeout: float = 180.0) -> list[Finding]:
    """Pide un embedding de prueba para cargar el modelo y comprobar su dimensión.

    Se hace antes de indexar: si el modelo no carga (VRAM ocupada, error CUDA),
    es mejor saberlo ahora que a mitad de un PDF de 2000 páginas.
    """
    try:
        reply = net.request_json(
            f"{config.url.rstrip('/')}/api/embed",
            method="POST",
            payload={"model": config.embedding, "input": "prueba", "keep_alive": "30m"},
            timeout=timeout,
        )
        dimension = len(reply["embeddings"][0])
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return [error(f"El embedding de prueba con {config.embedding} falla: {exc}")]
    if dimension != config.dimension:
        return [
            error(
                f"{config.embedding} devuelve vectores de {dimension} dimensiones; "
                f"atril.toml declara {config.dimension}."
            )
        ]
    return [ok(f"Embedding de prueba correcto ({dimension} dimensiones).")]


def app_path() -> Path | None:
    """Ruta de la aplicación de escritorio de Ollama en Windows, si existe."""
    if sys.platform != "win32":
        return None
    local = os.environ.get("LOCALAPPDATA")
    path = Path(local) / "Programs" / "Ollama" / "ollama app.exe" if local else None
    return path if path and path.is_file() else None


def launch_app(path: Path) -> None:
    """Abre la aplicación de Ollama sin esperar a que termine."""
    subprocess.Popen([str(path)], close_fds=True)
