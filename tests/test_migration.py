import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from support import EXAMPLES, write

from atril.config import load_station, load_syllabus
from atril.knowledge import Ledger, PlanState, ledger_path, plan
from atril.sources import Registry

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrar_estacion.py"
spec = importlib.util.spec_from_file_location("migrar_estacion", SCRIPT)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def old_station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Estación con la estructura de los scripts PowerShell."""
    monkeypatch.setattr(migration, "_port_busy", lambda port: False)
    root = tmp_path / "DeepTutor"
    mat = root / "materia_normativa"
    cte = mat / "fuentes" / "01_edificacion_CTE"
    write(cte / "CTE_DB-SI_2026-11.pdf", "%PDF si")
    write(cte / "GUIA_CTE_DB-SI_comentarios_2026-11.pdf", "%PDF guia si")
    write(cte / "Propio_2026-11.pdf", "%PDF propio")
    write(cte / "_LEEME.txt", "léeme")
    write(mat / "prompt-espacio.txt", "Eres un tutor")
    write(mat / "FUENTES.md", "# Fuentes")
    write(mat / ".deeptutor" / "data" / "user" / "chat_history.db", "chats")
    write(root / "deeptutor_app" / ".venv" / "Scripts" / "deeptutor.exe", "exe")
    write(root / "deeptutor_app" / "deeptutor" / "__init__.py", "")
    write(root / "lanzador" / "instalar.ps1", "ps1")
    write(root / "evaluaciones" / "normativa" / "cte-v2.jsonl", "{}\n")
    # KB vinculante con el DB-SI y, por error, la guía (debe quedar como retirada).
    raw = root / "data" / "knowledge_bases" / "norm-edificacion-cte" / "raw"
    for name in ("CTE_DB-SI_2026-11.pdf", "GUIA_CTE_DB-SI_comentarios_2026-11.pdf"):
        raw.mkdir(parents=True, exist_ok=True)
        shutil.copy(cte / name, raw / name)
    database = root / "data" / "user" / ".runtime" / "workspaces.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY, payload TEXT)")
        payload = {
            "workspace_id": "ws_1",
            "path": str(mat),
            "kind": "workspace",
            "display_name": "Normativa",
            "instructions": "Eres un tutor",
        }
        conn.execute(
            "INSERT INTO workspaces VALUES (?, ?)", ("ws_1", json.dumps(payload))
        )
    shutil.copy(EXAMPLES / "atril.toml", root / "atril.toml")
    text = (root / "atril.toml").read_text(encoding="utf-8")
    start, end = text.index("[deeptutor]"), text.index("[ollama]")
    (root / "atril.toml").write_text(
        text[:start] + "[deeptutor]\n\n" + text[end:], encoding="utf-8"
    )
    return root


def test_dry_run_changes_nothing(old_station: Path) -> None:
    before = sorted(p.relative_to(old_station) for p in old_station.rglob("*"))

    assert migration.main([str(old_station)]) == 0
    assert sorted(p.relative_to(old_station) for p in old_station.rglob("*")) == before


def test_apply_migrates_everything(old_station: Path) -> None:
    assert migration.main([str(old_station), "--aplicar"]) == 0

    syllabus_dir = old_station / "temarios" / "normativa"
    assert not (old_station / "deeptutor_app").exists()
    assert (
        old_station / "app" / ".venv.antes-de-migrar" / "Scripts" / "deeptutor.exe"
    ).is_file()
    assert (
        syllabus_dir / "espacio" / ".deeptutor" / "data" / "user" / "chat_history.db"
    ).is_file()
    assert (syllabus_dir / "prompt.md").read_text(encoding="utf-8") == "Eres un tutor"
    cte = syllabus_dir / "fuentes" / "01_edificacion_CTE"
    assert sorted(p.name for p in cte.iterdir()) == [
        "CTE_DB-SI.pdf",
        "GUIA_CTE_DB-SI_comentarios.pdf",
        "Propio_2026-11.pdf",  # desconocido: se queda, con aviso
    ]
    assert (
        old_station / "_legado" / "fuentes" / "01_edificacion_CTE" / "_LEEME.txt"
    ).is_file()
    assert (old_station / "_legado" / "lanzador" / "instalar.ps1").is_file()
    assert (syllabus_dir / "eval" / "cte-v2.jsonl").is_file()

    station = load_station(old_station)
    assert station.deeptutor.llm is not None
    assert station.deeptutor.packages == ("claude-agent-sdk>=0.2.174,<0.3",)
    assert (old_station / "atril.toml.antes-de-migrar").is_file()

    with sqlite3.connect(old_station / "data/user/.runtime/workspaces.sqlite3") as conn:
        (payload,) = conn.execute("SELECT payload FROM workspaces").fetchone()
    assert Path(json.loads(payload)["path"]) == syllabus_dir / "espacio"

    syllabus = load_syllabus(syllabus_dir)
    assert Registry(syllabus.registry_file).get("cte-db-si") is not None
    ledger = Ledger(ledger_path(syllabus))
    states = {
        item.source_id: item.state
        for item in plan(syllabus, syllabus.knowledge_bases[0], ledger)
    }
    assert states["cte-db-si"] is PlanState.INDEXED
    assert states["loe"] is PlanState.MISSING
    retired = [key for key, state in states.items() if state is PlanState.REMOVED]
    assert retired == ["legado-guia-cte-db-si-comentarios-2026-11"]


def test_refuses_when_already_migrated(old_station: Path) -> None:
    assert migration.main([str(old_station), "--aplicar"]) == 0
    assert migration.main([str(old_station), "--aplicar"]) == 1


def test_reports_failed_step(
    old_station: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(*args: object, **kwargs: object) -> None:
        raise PermissionError("[WinError 32] El proceso no tiene acceso al archivo")

    monkeypatch.setattr(migration.shutil, "move", locked)

    assert migration.main([str(old_station), "--aplicar"]) == 1
    assert (old_station / "deeptutor_app").is_dir()  # nada se ha movido ni borrado
