import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from support import write

from atril import install
from atril.checks import Level
from atril.config import load_station
from atril.install import Installer, StepError, doctor_findings, setup_payload
from atril.ollama import OllamaStatus


class Recorder:
    """Sustituye a run_command/capture y registra los comandos (sin ruta)."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.outputs: dict[str, str] = {}
        self.codes: dict[str, int] = {}
        self.files: dict[str, str] = {}

    @staticmethod
    def _key(command: Sequence[str]) -> list[str]:
        return [Path(command[0]).name, *command[1:]]

    def run(
        self,
        command: Sequence[str],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        key = self._key(command)
        self.commands.append(key)
        for arg in command:  # guarda el JSON de config apply antes de que se borre
            if arg.endswith("setup.json"):
                self.files["setup.json"] = Path(arg).read_text(encoding="utf-8")
        return self.codes.get(key[1] if len(key) > 1 else key[0], 0)

    def capture(
        self,
        command: Sequence[str],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        *,
        check: bool = True,
    ) -> str:
        key = self._key(command)
        self.commands.append(key)
        for fragment, output in self.outputs.items():
            if fragment in " ".join(key):
                return output
        return ""


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(install, "run_command", rec.run)
    monkeypatch.setattr(install, "capture", rec.capture)
    monkeypatch.setattr(install.shutil, "which", lambda name: f"/bin/{name}")
    return rec


def _installer(station_dir: Path) -> Installer:
    return Installer(load_station(station_dir), env={"DEEPTUTOR_HOME": "x"})


def test_setup_payload(station_dir: Path) -> None:
    payload = setup_payload(load_station(station_dir))

    assert payload == {
        "embedding": {
            "provider": "ollama",
            "model": "qwen3-embedding:8b",
            "base_url": "http://localhost:11434/api/embed",
            "dimension": 4096,
        },
        "system": {"backend_port": 8001, "frontend_port": 3782},
        "llm": {"provider": "claude_code", "model": "claude-code/opus"},
        "search": {"provider": "duckduckgo"},
    }


def test_doctor_findings() -> None:
    report: dict[str, Any] = {
        "checks": [
            {"label": "LLM", "status": "pass", "detail": "ok", "required": True},
            {"label": "RAG", "status": "skip", "detail": "sin KB", "required": False},
            {"label": "Red", "status": "fail", "detail": "x", "required": False},
            {"label": "Disco", "status": "fail", "detail": "y", "required": True},
        ]
    }

    levels = [finding.level for finding in doctor_findings(report)]

    assert levels == [Level.OK, Level.INFO, Level.WARNING, Level.ERROR]


def test_clone_new(station_dir: Path, recorder: Recorder) -> None:
    finding = _installer(station_dir).clone()

    assert finding.level is Level.OK
    clone = recorder.commands[0]
    assert clone[:6] == ["git", "-c", "core.longpaths=true", "clone", "--depth", "1"]
    assert clone[6:9] == ["--branch", "dev", "https://github.com/HKUDS/DeepTutor"]
    assert recorder.commands[1][-3:] == ["config", "core.longpaths", "true"]


def test_clone_existing_checkout(station_dir: Path, recorder: Recorder) -> None:
    (station_dir / "app" / ".git").mkdir(parents=True)
    _origin(recorder)

    assert _installer(station_dir).clone().level is Level.INFO
    assert [c[3] for c in recorder.commands] == ["remote", "branch"]


def test_clone_refuses_existing_checkout_of_other_repo(
    station_dir: Path, recorder: Recorder
) -> None:
    (station_dir / "app" / ".git").mkdir(parents=True)
    _origin(recorder, "https://github.com/otro/DeepTutor")

    with pytest.raises(StepError, match="sigue"):
        _installer(station_dir).clone()


def test_clone_refuses_foreign_folder(station_dir: Path, recorder: Recorder) -> None:
    write(station_dir / "app" / "algo.txt", "x")

    with pytest.raises(StepError, match="no es un checkout"):
        _installer(station_dir).clone()


def test_python_env_creates_venv_and_installs(
    station_dir: Path, recorder: Recorder
) -> None:
    findings = _installer(station_dir).python_env(docling=True)

    names = [command[1:4] for command in recorder.commands]
    assert names[0] == ["venv", "--clear", "--seed"]
    assert recorder.commands[1][-2:] == ["-r", "requirements/full.txt"]
    assert recorder.commands[2][-3:] == ["-e", ".", "--no-deps"]
    assert recorder.commands[3][-1] == "claude-agent-sdk>=0.2.174,<0.3"
    assert recorder.commands[4][-2:] == list(install.DOCLING_PACKAGES)
    assert [f.level for f in findings] == [Level.OK, Level.OK, Level.OK]


def test_python_env_without_docling(station_dir: Path, recorder: Recorder) -> None:
    write(load_station(station_dir).venv_python, "")

    findings = _installer(station_dir).python_env(docling=False)

    assert not any("docling" in " ".join(c) for c in recorder.commands)
    assert findings[-1].level is Level.WARNING


def test_failed_step_raises(station_dir: Path, recorder: Recorder) -> None:
    recorder.codes["venv"] = 2

    with pytest.raises(StepError, match="uv venv ha fallado"):
        _installer(station_dir).python_env(docling=False)


def test_frontend(station_dir: Path, recorder: Recorder) -> None:
    installer = _installer(station_dir)
    assert installer.frontend().level is Level.OK
    assert recorder.commands[-1][:2] == ["npm", "ci"]

    (installer.web_dir / "node_modules").mkdir(parents=True)
    assert installer.frontend().level is Level.INFO
    assert installer.frontend(force=True).level is Level.OK
    assert len(recorder.commands) == 2


def test_embedding_model(
    station_dir: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = _installer(station_dir)
    statuses = iter(
        [
            OllamaStatus(running=False),
            OllamaStatus(True, "0.12.0", ("qwen3-embedding:8b",)),
            OllamaStatus(True, "0.12.0", ()),
        ]
    )
    monkeypatch.setattr(install.ollama, "get_status", lambda url: next(statuses))

    assert installer.embedding_model().level is Level.WARNING
    assert installer.embedding_model().level is Level.OK
    assert recorder.commands == []
    installer.embedding_model()
    assert recorder.commands == [["ollama", "pull", "qwen3-embedding:8b"]]


def test_configure(station_dir: Path, recorder: Recorder) -> None:
    _installer(station_dir).configure()

    subcommands = [command[1:3] for command in recorder.commands]
    assert subcommands == [["init", "--home"], ["config", "apply"], ["config", "apply"]]
    assert recorder.commands[1][-1] == "--check"
    assert json.loads(recorder.files["setup.json"])["llm"]["provider"] == "claude_code"


def test_runtime_settings_warns_on_chunk_change(
    station_dir: Path, recorder: Recorder
) -> None:
    before = {"chunk_size": 512, "chunk_overlap": 50, "parser": "text_only"}
    recorder.outputs["-c"] = "aviso de DeepTutor\n" + json.dumps(before) + "\n"

    findings = _installer(station_dir).runtime_settings()

    sent = json.loads(recorder.commands[0][-1])
    assert sent == {
        "parser": "docling",
        "chunk_size": 1024,
        "chunk_overlap": 150,
        "download_models": True,
        "batch_size": 10,
        "batch_delay": 0.0,
    }
    assert [f.level for f in findings] == [Level.OK, Level.WARNING]
    assert "512/50 → 1024/150" in findings[1].message


def test_update_checkout(
    station_dir: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    heads = iter(["aaa1 viejo", "bbb2 nuevo"])
    installer = _installer(station_dir)
    _origin(recorder)
    monkeypatch.setattr(Installer, "head", lambda self: next(heads))

    assert installer.update_checkout() == ("aaa1 viejo", "bbb2 nuevo")
    tail = [c[3:] for c in recorder.commands if c[3] in {"fetch", "reset"}]
    assert tail == [
        ["fetch", "--depth", "1", "origin", "dev"],
        ["reset", "--hard", "FETCH_HEAD"],
    ]


def _origin(
    recorder: Recorder,
    url: str = "git@github.com:hkuds/DeepTutor.git",
    branch: str = "dev",
) -> None:
    recorder.outputs["remote get-url"] = url + "\n"
    recorder.outputs["branch --show-current"] = branch + "\n"


@pytest.mark.parametrize(
    ("url", "branch", "message"),
    [
        ("https://github.com/otro/DeepTutor", "dev", "sigue"),
        ("https://github.com/HKUDS/DeepTutor.git", "main", "rama"),
    ],
)
def test_update_checkout_refuses_other_origin(
    station_dir: Path, recorder: Recorder, url: str, branch: str, message: str
) -> None:
    _origin(recorder, url, branch)

    with pytest.raises(StepError, match=message):
        _installer(station_dir).update_checkout()
    assert not any(c[3] in {"fetch", "reset"} for c in recorder.commands)


def test_same_remote() -> None:
    assert install.same_remote(
        "ssh://git@github.com/HKUDS/DeepTutor.git",
        "https://github.com/hkuds/deeptutor/",
    )
    assert not install.same_remote(
        "https://github.com/HKUDS/DeepTutor", "https://github.com/HKUDS/DeepTutor-x"
    )


def test_python_env_recreates_venv_with_other_version(
    station_dir: Path, recorder: Recorder
) -> None:
    write(load_station(station_dir).venv_python, "")
    recorder.outputs["sys.version_info"] = "3.12\n"

    findings = _installer(station_dir).python_env(docling=False)

    assert ["venv", "--clear", "--seed"] in [c[1:4] for c in recorder.commands]
    assert "3.12" in findings[0].message


def test_python_env_keeps_matching_venv(station_dir: Path, recorder: Recorder) -> None:
    write(load_station(station_dir).venv_python, "")
    recorder.outputs["sys.version_info"] = "3.13\n"

    _installer(station_dir).python_env(docling=False)

    assert not any(c[1] == "venv" for c in recorder.commands)


def test_version_finding(tmp_path: Path) -> None:
    assert install.version_finding(tmp_path).level is Level.WARNING
    write(tmp_path / "deeptutor" / "__version__.py", '__version__ = "1.7.1"\n')
    assert install.version_finding(tmp_path).level is Level.OK
    write(tmp_path / "deeptutor" / "__version__.py", "__version__ = '2.0.0'\n")
    assert "2.0.0" in install.version_finding(tmp_path).message


def test_doctor_rejects_unknown_json(station_dir: Path, recorder: Recorder) -> None:
    recorder.outputs["doctor"] = '{"resultado": "ok"}'

    with pytest.raises(StepError, match="formato esperado"):
        _installer(station_dir).doctor()


def test_update_checkout_refuses_dirty_tree(
    station_dir: Path, recorder: Recorder
) -> None:
    _origin(recorder)
    recorder.outputs["status"] = " M deeptutor/x.py\n"

    with pytest.raises(StepError, match="cambios locales"):
        _installer(station_dir).update_checkout()


def test_doctor_parses_json_after_noise(station_dir: Path, recorder: Recorder) -> None:
    report = {"checks": [{"label": "LLM", "status": "pass", "detail": "ok"}]}
    recorder.outputs["doctor"] = "﻿" + json.dumps(report)

    assert [f.level for f in _installer(station_dir).doctor()] == [Level.OK]


def test_capture_check(tmp_path: Path) -> None:
    script = tmp_path / "falla.py"
    script.write_text("import sys\nprint('{\"ok\": false}')\nsys.exit(1)\n")
    command = [sys.executable, str(script)]

    with pytest.raises(StepError, match="ha fallado"):
        install.capture(command)
    assert json.loads(install.capture(command, check=False)) == {"ok": False}


def test_doctor_rejects_malformed_check(station_dir: Path, recorder: Recorder) -> None:
    recorder.outputs["doctor"] = '{"checks": ["no es un objeto"]}'

    with pytest.raises(StepError, match="formato"):
        _installer(station_dir).doctor()
