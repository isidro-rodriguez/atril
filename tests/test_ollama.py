from typing import Any

import pytest

from atril import ollama
from atril.checks import Level
from atril.config.station import OllamaConfig
from atril.ollama import LoadedModel, OllamaStatus

CONFIG = OllamaConfig("http://localhost:11434", "qwen3-embedding:8b", 4096, 8192)


def _levels(status: OllamaStatus) -> list[Level]:
    return [finding.level for finding in ollama.check(status, CONFIG)]


@pytest.fixture(autouse=True)
def _no_env_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_CONTEXT_LENGTH", raising=False)


def test_not_running() -> None:
    assert _levels(OllamaStatus(running=False)) == [Level.ERROR]


def test_healthy() -> None:
    status = OllamaStatus(True, "0.12.0", ("qwen3-embedding:8b",))

    assert _levels(status) == [Level.OK, Level.OK]


def test_missing_embedding() -> None:
    findings = ollama.check(OllamaStatus(True, "0.12.0", ("llama3:8b",)), CONFIG)

    assert findings[1].level is Level.ERROR
    assert "ollama pull qwen3-embedding:8b" in findings[1].message


def test_foreign_model_and_context_mismatch() -> None:
    status = OllamaStatus(
        True,
        "0.12.0",
        ("qwen3-embedding:8b", "qwen3.5:9b"),
        (
            LoadedModel("qwen3.5:9b", 6 * 1024**3, 4096),
            LoadedModel("qwen3-embedding:8b", 5 * 1024**3, 4096),
        ),
    )

    findings = ollama.check(status, CONFIG)

    assert [f.level for f in findings] == [
        Level.OK,
        Level.OK,
        Level.WARNING,
        Level.INFO,
        Level.WARNING,
    ]
    assert "qwen3.5:9b" in findings[2].message
    assert "4096" in findings[4].message


def test_env_context_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_LENGTH", "4096")
    status = OllamaStatus(True, "0.12.0", ("qwen3-embedding:8b",))

    assert _levels(status)[-1] is Level.WARNING


def test_get_status(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: dict[str, Any] = {
        "/api/version": {"version": "0.12.0"},
        "/api/tags": {"models": [{"name": "qwen3-embedding:8b"}]},
        "/api/ps": {
            "models": [
                {"name": "qwen3-embedding:8b", "size_vram": 10, "context_length": 8192}
            ]
        },
    }
    monkeypatch.setattr(
        ollama.net,
        "get_json",
        lambda url, timeout: responses[url.removeprefix("http://x:1")],
    )

    status = ollama.get_status("http://x:1/")

    assert status == OllamaStatus(
        True,
        "0.12.0",
        ("qwen3-embedding:8b",),
        (LoadedModel("qwen3-embedding:8b", 10, 8192),),
    )


def test_get_status_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, timeout: float) -> Any:
        raise ConnectionRefusedError

    monkeypatch.setattr(ollama.net, "get_json", refuse)

    assert ollama.get_status("http://x:1") == OllamaStatus(running=False)
