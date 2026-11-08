from pathlib import Path

import pytest
from support import write
from typer.testing import CliRunner

from atril import install
from atril.config import load_station, load_syllabus
from atril.errors import AtrilError
from atril.main import app
from atril.ops import Recorder, service
from atril.ops import syllabus as operations

runner = CliRunner()
PDF = b"%PDF-1.7\n contenido\n"


def _pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PDF)
    return path


def _invoke(station: Path, *args: str):
    return runner.invoke(app, [*args], env={"ATRIL_ESTACION": str(station)})


def _without_ollama(station: Path) -> None:
    text = (station / "atril.toml").read_text(encoding="utf-8")
    start = text.index("[ollama]")
    end = text.index("\n[", start + 1)
    (station / "atril.toml").write_text(text[:start] + text[end + 1 :], "utf-8")


# --- crear ----------------------------------------------------------------------


def test_create_syllabus(station_dir: Path) -> None:
    station = load_station(station_dir)

    syllabus = operations.create(station, "Matemáticas II")

    assert syllabus.id == "matematicas-ii"
    assert [kb.id for kb in syllabus.knowledge_bases] == ["matematicas-ii"]
    assert syllabus.knowledge_bases[0].patterns == ("*",)
    assert (syllabus.root / "prompt.md").is_file()
    assert syllabus.sources_dir.is_dir()


def test_create_refuses_existing_syllabus_or_kb(station_dir: Path) -> None:
    station = load_station(station_dir)

    with pytest.raises(AtrilError, match="ya existe el temario"):
        operations.create(station, "Otra", "normativa")
    with pytest.raises(AtrilError, match="ya hay una KB"):
        operations.create(station, "CTE", "norm-edificacion-cte")
    assert not (station.syllabi_dir / "norm-edificacion-cte").exists()


# --- añadir ---------------------------------------------------------------------


def test_add_local_pdf_to_new_syllabus(station_dir: Path, tmp_path: Path) -> None:
    syllabus = operations.create(load_station(station_dir), "Historia")

    source = operations.add_source(syllabus, str(_pdf(tmp_path / "Tema 1.pdf")))

    assert source.id == "tema-1"
    assert source.is_manual
    assert (syllabus.sources_dir / "historia" / "Tema 1.pdf").read_bytes() == PDF
    again = operations.add_source(syllabus, str(_pdf(tmp_path / "b" / "Tema 1 .pdf")))
    assert again.id == "tema-1-2"  # id repetido: se numera
    assert len(load_syllabus(syllabus.root).sources) == 2


def test_add_keeps_comments_and_extends_kb_patterns(
    station_dir: Path, tmp_path: Path
) -> None:
    root = station_dir / "temarios" / "normativa"
    syllabus = load_syllabus(root)

    source = operations.add_source(
        syllabus,
        str(_pdf(tmp_path / "rite.pdf")),
        title="RITE",
        kb_id="norm-edificacion-cte-guias",
    )

    text = (root / "temario.toml").read_text(encoding="utf-8")
    assert "# Cada fuente pertenece a una sola KB" in text  # comentarios intactos
    assert source.id == "rite"
    reloaded = load_syllabus(root)
    assert reloaded.kb_of(source).id == "norm-edificacion-cte-guias"


def test_add_url_derives_file_name(station_dir: Path) -> None:
    syllabus = operations.create(load_station(station_dir), "Leyes")

    named = operations.add_source(syllabus, "https://boe.es/pdf/ley-39.pdf")
    unnamed = operations.add_source(
        syllabus, "https://ejemplo.org/descarga?id=4", title="Decreto 4"
    )

    assert (named.url, named.filename) == (
        "https://boe.es/pdf/ley-39.pdf",
        "ley-39.pdf",
    )
    assert (unnamed.id, unnamed.filename) == ("decreto-4", "decreto-4.pdf")


def test_add_rejects_bad_input_without_changes(
    station_dir: Path, tmp_path: Path
) -> None:
    root = station_dir / "temarios" / "normativa"
    syllabus = load_syllabus(root)
    before = (root / "temario.toml").read_text(encoding="utf-8")
    pdf = str(_pdf(tmp_path / "x.pdf"))

    with pytest.raises(AtrilError, match="no es un PDF"):
        operations.add_source(syllabus, str(write(tmp_path / "x.txt", "hola")))
    with pytest.raises(AtrilError, match="indica la KB"):
        operations.add_source(syllabus, pdf)
    with pytest.raises(AtrilError, match="no encaja"):  # el id cae también en otra KB
        operations.add_source(
            syllabus, pdf, source_id="cte-nuevo", kb_id="norm-edificacion-cte-guias"
        )

    assert (root / "temario.toml").read_text(encoding="utf-8") == before
    assert not list(syllabus.sources_dir.rglob("x.pdf"))


def test_cli_create_add_and_validate(station_dir: Path, tmp_path: Path) -> None:
    created = _invoke(station_dir, "temario", "crear", "Física")
    assert created.exit_code == 0, created.output
    assert "Temario fisica creado" in created.output

    added = _invoke(
        station_dir, "fuentes", "añadir", "fisica", str(_pdf(tmp_path / "ondas.pdf"))
    )
    assert added.exit_code == 0, added.output
    assert "Fuente ondas añadida a la KB fisica" in added.output
    assert _invoke(station_dir, "validar").exit_code == 0


# --- Ollama opcional ---------------------------------------------------------------


def test_station_without_ollama(station_dir: Path) -> None:
    _without_ollama(station_dir)
    station = load_station(station_dir)

    assert station.ollama is None
    assert "embedding" not in install.setup_payload(station)
    assert service.ensure_ollama(station, Recorder()) == []
    sections = dict(service.status(station, Recorder()))
    assert "no se indexan fuentes" in sections["Ollama"][0].message


def test_index_requires_ollama(station_dir: Path) -> None:
    _without_ollama(station_dir)
    write(load_station(station_dir).deeptutor_cli, "")
    root = station_dir / "temarios" / "normativa"
    _pdf(root / "fuentes" / "01_edificacion_CTE" / "DBSI.pdf")  # pendiente de indexar

    result = _invoke(station_dir, "kb", "indexar", "normativa")

    assert result.exit_code == 1
    assert "falta [ollama]" in result.output
