import json
import sys
from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import evaluation
from atril.checks import ok
from atril.commands import knowledge as commands
from atril.config import load_station
from atril.config.station import Station
from atril.evaluation import (
    EvalCase,
    EvalReport,
    EvaluationError,
    Hit,
    previous_report,
    run_evaluation,
)
from atril.main import app

DT_REPORT = {
    "metrics": {
        "recall@5": 0.5,
        "mrr": 0.25,
        "queries_failed": 0,
        "provider": "llamaindex",
    },
    "queries": [
        {
            "case_id": "si-01",
            "query": "¿Anchura de puerta?",
            "matched_gold": [False, True],
        },
        {"case_id": "si-02", "query": "¿Sector?", "matched_gold": [False, False]},
        {
            "case_id": "si-03",
            "query": "¿Error?",
            "matched_gold": [],
            "error": "timeout",
        },
    ],
    "trace": {"¿Sector?": [[["DBSI.pdf", "11", 0.03], ["DBSUA.pdf", "", 0.01]]]},
}

runner = CliRunner()


def test_report_from_deeptutor() -> None:
    report = EvalReport.from_deeptutor(DT_REPORT, "kb", "cte.jsonl", 5)

    assert [(c.case_id, c.rank, c.error) for c in report.cases] == [
        ("si-01", 2, ""),
        ("si-02", None, ""),
        ("si-03", None, "timeout"),
    ]
    assert report.cases[1].hits[0] == Hit("DBSI.pdf", "11", 0.03)
    assert report.metrics == {"recall@5": 0.5, "mrr": 0.25, "queries_failed": 0}


def test_repeated_query_keeps_each_trace() -> None:
    data = {
        "queries": [
            {"case_id": "a", "query": "¿Rampa?", "matched_gold": [True]},
            {"case_id": "b", "query": "¿Rampa?", "matched_gold": [True]},
        ],
        "trace": {"¿Rampa?": [[["uno.pdf", "1", 0.5]], [["dos.pdf", "2", 0.4]]]},
    }

    report = EvalReport.from_deeptutor(data, "kb", "x.jsonl", 5)

    assert [case.hits[0].title for case in report.cases] == ["uno.pdf", "dos.pdf"]


def test_save_load_and_previous(tmp_path: Path) -> None:
    first = EvalReport("kb", "cte.jsonl", 5, "2026-11-01T10:00:00+00:00", {"mrr": 0.5})
    older = EvalReport("kb", "cte.jsonl", 5, "2026-10-01T10:00:00+00:00", {"mrr": 0.1})
    first.cases.append(EvalCase("a", "q", 1, hits=(Hit("x.pdf", "3", 0.1),)))
    other_k = EvalReport(
        "kb", "cte.jsonl", 3, "2026-11-02T10:00:00+00:00", {"mrr": 0.9}
    )
    other_set = EvalReport(
        "kb", "otro.jsonl", 5, "2026-11-03T10:00:00+00:00", {"mrr": 0.1}
    )
    for report in (older, first, other_k, other_set):
        report.save(tmp_path)
    write(tmp_path / "kb-roto.json", "no es json")

    found = previous_report(tmp_path, "kb", "cte.jsonl", 5)

    assert found == first
    assert (tmp_path / "kb-20261101-100000.json").is_file()
    assert previous_report(tmp_path, "kb", "nuevo.jsonl", 5) is None


@pytest.fixture
def fake_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """El 'Python de app/' es el de los tests."""
    monkeypatch.setattr(
        Station, "venv_python", property(lambda self: Path(sys.executable))
    )


def test_run_evaluation_reports_progress(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch, fake_python: None
) -> None:
    script = (
        "import json, sys\n"
        f"for i in range(3): print('{evaluation.PROGRESS_PREFIX}', i, 3, flush=True)\n"
        f"open(sys.argv[4], 'w').write(json.dumps({DT_REPORT!r}))\n"
    )
    monkeypatch.setattr(evaluation, "_EVAL_SCRIPT", script)
    seen: list[tuple[int, int]] = []

    report = run_evaluation(
        load_station(station_dir),
        {},
        "kb",
        Path("cte.jsonl"),
        5,
        lambda d, t: seen.append((d, t)),
    )

    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert report.dataset == "cte.jsonl"
    assert len(report.cases) == 3


def test_run_evaluation_failure(
    station_dir: Path, monkeypatch: pytest.MonkeyPatch, fake_python: None
) -> None:
    script = (
        "import sys; sys.stderr.write('ModuleNotFoundError: deeptutor\\n'); sys.exit(1)"
    )
    monkeypatch.setattr(evaluation, "_EVAL_SCRIPT", script)

    with pytest.raises(EvaluationError, match="ModuleNotFoundError"):
        run_evaluation(load_station(station_dir), {}, "kb", Path("x.jsonl"), 5)


@pytest.fixture
def evaluable(station_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """KB existente con su conjunto de preguntas y evaluación simulada."""
    station = load_station(station_dir)
    write(station.deeptutor_cli, "")
    write(station.kb_dir("norm-edificacion-cte") / "metadata.json", "{}")
    write(station.syllabi_dir / "normativa" / "eval" / "cte-v2.jsonl", "{}\n")
    monkeypatch.setattr(commands, "_embedding_preflight", lambda station: [ok("embed")])
    return station_dir


def _fake_runs(monkeypatch: pytest.MonkeyPatch, *metrics: dict) -> None:
    reports = iter(metrics)

    def fake(station, env, kb, dataset, k, progress=None):
        data = dict(DT_REPORT, metrics=next(reports))
        if progress:
            progress(3, 3)
        return EvalReport.from_deeptutor(data, kb, dataset.name, k)

    monkeypatch.setattr(commands, "run_evaluation", fake)


def test_evaluate_command_saves_and_compares(
    evaluable: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_runs(
        monkeypatch,
        {"mrr": 0.5, "queries_failed": 1},
        {"mrr": 0.75, "queries_failed": 0},
    )
    args = ["kb", "evaluar", "norm-edificacion-cte"]

    first = runner.invoke(app, args, env={"ATRIL_ESTACION": str(evaluable)})
    assert first.exit_code == 1  # si-03 tiene error
    assert "rango 2" in first.output
    assert "DBSI.pdf p.11" in first.output
    assert "Anterior" not in first.output

    second = runner.invoke(app, args, env={"ATRIL_ESTACION": str(evaluable)})
    assert "Anterior" in second.output
    assert "+0.250" in second.output
    assert "-1" in second.output
    folder = load_station(evaluable).syllabi_dir / "normativa" / "eval" / "informes"
    assert len(list(folder.glob("norm-edificacion-cte-*.json"))) == 2


def test_evaluate_requires_kb_and_dataset(evaluable: Path) -> None:
    args = ["kb", "evaluar", "norm-edificacion-cte-guias"]
    result = runner.invoke(app, args, env={"ATRIL_ESTACION": str(evaluable)})
    assert result.exit_code == 1
    assert "aún no existe" in result.output

    station = load_station(evaluable)
    write(station.kb_dir("norm-edificacion-cte-guias") / "metadata.json", "{}")
    result = runner.invoke(app, args, env={"ATRIL_ESTACION": str(evaluable)})
    assert result.exit_code == 1
    assert "no declara 'evaluacion'" in result.output


def test_evaluate_with_explicit_dataset(
    evaluable: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_runs(monkeypatch, {"mrr": 1.0})
    dataset = tmp_path / "otro.jsonl"
    dataset.write_text(json.dumps({"id": "x"}) + "\n")

    args = ["kb", "evaluar", "norm-edificacion-cte", "--dataset", str(dataset)]
    result = runner.invoke(app, [*args], env={"ATRIL_ESTACION": str(evaluable)})

    assert "Métricas" in result.output
    folder = load_station(evaluable).syllabi_dir / "normativa" / "eval" / "informes"
    (saved,) = folder.glob("*.json")
    assert EvalReport.load(saved).dataset == "otro.jsonl"
