"""Evaluación de la recuperación de una KB con su conjunto de preguntas.

Se usa el evaluador de DeepTutor con una diferencia: ``deeptutor kb eval``
compara las respuestas esperadas con ``content``, que LlamaIndex recorta a 200
caracteres; aquí se compara con ``evidence_text`` (el texto completo del chunk).
Por eso se ejecuta con el Python de ``app/`` (la excepción prevista en las
decisiones de diseño) y no con el CLI.

Los informes se guardan en ``temarios/<t>/eval/informes/``, fuera de
``espacio/``: lo que está dentro del espacio lo lee el agente.
"""

import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from acodo.utils import get_now

from atril.config.station import Station
from atril.config.syllabus import Syllabus
from atril.processes import kill_tree

PROGRESS_PREFIX = "ATRIL-PROGRESS"
"""Marca de las líneas de avance que emite el script."""

_EVAL_SCRIPT = f"""
import asyncio, json, sys
from pathlib import Path
from deeptutor.services.rag.eval.dataset import load_dataset
from deeptutor.services.rag.eval.runner import evaluate_dataset
from deeptutor.tools.rag_tool import rag_search

kb, dataset_path, k, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
trace = {{}}

async def search(query, *, kb_name, kb_base_dir=None, mode=None, top_k=5,
                 rewrite=None, **extra):
    kwargs = {{"top_k": top_k}}
    if mode:
        kwargs["mode"] = mode
    if rewrite is not None:
        kwargs["rewrite"] = rewrite
    result = dict(await rag_search(query=query, kb_name=kb_name,
                                   kb_base_dir=kb_base_dir, **kwargs))
    sources = []
    for source in result.get("sources") or []:
        source = dict(source)
        source["content"] = source.get("evidence_text") or source.get("content") or ""
        sources.append(source)
    result["sources"] = sources
    # Lista por pregunta: un dataset puede repetir la misma pregunta.
    trace.setdefault(query, []).append([
        [s.get("title", ""), s.get("page_label") or s.get("page") or "", s.get("score")]
        for s in sources[:top_k]
    ])
    return result

def progress(index, total, evaluation):
    print("{PROGRESS_PREFIX}", index, total, flush=True)

async def main():
    dataset = load_dataset(dataset_path)
    report = await evaluate_dataset(dataset, kb_name=kb, k=k, search_fn=search,
                                    provider="llamaindex", progress=progress)
    data = report.to_dict()
    data["trace"] = trace
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

asyncio.run(main())
"""
"""Evaluación con texto completo; argumentos: kb, dataset, k, fichero de salida."""

Progress = Callable[[int, int], None]
"""Avance: casos evaluados y total."""


class EvaluationError(Exception):
    """La evaluación no ha podido completarse; el mensaje está en español."""


@dataclass(frozen=True, slots=True)
class Hit:
    """Fragmento recuperado para una pregunta."""

    title: str
    page: str
    score: float | None


@dataclass(frozen=True, slots=True)
class EvalCase:
    """Resultado de una pregunta."""

    case_id: str
    query: str
    rank: int | None
    """Posición del primer fragmento que contiene la respuesta (``None``: no está)."""
    error: str = ""
    hits: tuple[Hit, ...] = ()


@dataclass(slots=True)
class EvalReport:
    """Informe de una evaluación."""

    kb: str
    dataset: str
    k: int
    created_at: str
    metrics: dict[str, float | int]
    cases: list[EvalCase] = field(default_factory=list)

    @classmethod
    def from_deeptutor(
        cls, data: dict[str, Any], kb: str, dataset: str, k: int
    ) -> "EvalReport":
        """Construye el informe a partir del JSON del evaluador de DeepTutor."""
        # Cada pregunta repetida consume su traza en orden.
        traces = {text: iter(runs) for text, runs in (data.get("trace") or {}).items()}
        cases = []
        for query in data.get("queries", []):
            matched = query.get("matched_gold") or []
            rank = next((n for n, hit in enumerate(matched, 1) if hit), None)
            run = next(traces.get(str(query.get("query", "")), iter(())), [])
            hits = tuple(
                Hit(str(title), str(page), score) for title, page, score in run
            )
            cases.append(
                EvalCase(
                    case_id=str(query.get("case_id", "?")),
                    query=str(query.get("query", "")),
                    rank=rank,
                    error=str(query.get("error") or ""),
                    hits=hits,
                )
            )
        metrics = {
            key: value
            for key, value in (data.get("metrics") or {}).items()
            if isinstance(value, int | float)
        }
        return cls(kb, dataset, k, get_now().isoformat(), metrics, cases)

    @classmethod
    def load(cls, path: Path) -> "EvalReport":
        """Lee un informe guardado por atril."""
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = [
            EvalCase(
                case["case_id"],
                case["query"],
                case["rank"],
                case.get("error", ""),
                tuple(Hit(**hit) for hit in case.get("hits", [])),
            )
            for case in data.get("cases", [])
        ]
        return cls(
            data["kb"],
            data["dataset"],
            data["k"],
            data["created_at"],
            data["metrics"],
            cases,
        )

    def save(self, folder: Path) -> Path:
        """Guarda el informe como ``<kb>-<AAAAMMDD-HHMMSS>.json`` en ``folder``."""
        folder.mkdir(parents=True, exist_ok=True)
        stamp = self.created_at[:19].replace("-", "").replace(":", "").replace("T", "-")
        path = folder / f"{self.kb}-{stamp}.json"
        counter = 2
        while path.exists():
            path = folder / f"{self.kb}-{stamp}-{counter}.json"
            counter += 1
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        return path


def reports_dir(syllabus: Syllabus) -> Path:
    """Carpeta de informes de evaluación del temario."""
    return syllabus.root / "eval" / "informes"


def previous_report(folder: Path, kb: str, dataset: str, k: int) -> EvalReport | None:
    """Último informe guardado (por fecha) de la misma KB, preguntas y ``k``."""
    reports = []
    for path in folder.glob(f"{kb}-*.json"):
        try:
            report = EvalReport.load(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if report.kb == kb and report.dataset == dataset and report.k == k:
            reports.append(report)
    if not reports:
        return None
    return max(reports, key=lambda report: report.created_at)


def run_evaluation(
    station: Station,
    env: dict[str, str],
    kb: str,
    dataset: Path,
    k: int,
    progress: Progress | None = None,
) -> EvalReport:
    """Ejecuta la evaluación con el Python de ``app/``.

    Raises:
        EvaluationError: Si el script falla o no produce informe.
    """
    station.logs_dir.mkdir(parents=True, exist_ok=True)
    output = station.logs_dir / f"evaluacion-{kb}.json"
    log = station.logs_dir / f"evaluacion-{kb}.log"
    output.unlink(missing_ok=True)
    command = [
        str(station.venv_python),
        "-X",
        "utf8",
        "-c",
        _EVAL_SCRIPT,
        kb,
        str(dataset),
        str(k),
        str(output),
    ]
    with log.open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
            env=env,
        )
        try:
            for line in process.stdout or ():
                parts = line.split()
                if len(parts) == 3 and parts[0] == PROGRESS_PREFIX and progress:
                    done, total = int(parts[1]), int(parts[2])
                    progress(min(done + 1, total), total)
            process.wait()
        except BaseException:
            kill_tree(process.pid)
            raise
    if process.returncode != 0 or not output.is_file():
        tail = (
            log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:]
        )
        detail = tail[0] if tail else f"código {process.returncode}"
        raise EvaluationError(f"la evaluación ha fallado: {detail} (log: {log})")
    data = json.loads(output.read_text(encoding="utf-8"))
    return EvalReport.from_deeptutor(data, kb, dataset.name, k)
