from pathlib import Path

import pytest
from support import write

from atril.config import ConfigError, load_syllabi, load_syllabus
from atril.config.syllabus import CheckFrequency, SourceKind

HEAD = '[temario]\nnombre = "Prueba"\n'
KB = '[[kb]]\nid = "kb-a"\nvinculante = true\nfuentes = ["*"]\n'


def _syllabus(tmp_path: Path, body: str, name: str = "prueba") -> Path:
    root = tmp_path / name
    write(root / "temario.toml", HEAD + body)
    return root


def test_example_syllabus_is_valid(station_dir: Path) -> None:
    syllabus = load_syllabus(station_dir / "temarios" / "normativa")
    binding, guides = syllabus.knowledge_bases

    assert syllabus.id == "normativa"
    assert [s.id for s in syllabus.sources_of(binding)] == ["cte-db-si", "loe"]
    assert [s.id for s in syllabus.sources_of(guides)] == ["guia-cte-si"]
    assert binding.eval_file == "eval/cte-v2.jsonl"
    assert syllabus.warnings == ()

    cte, _, guide = syllabus.sources
    assert cte.filename == "DBSI.pdf"  # deducido de la URL
    assert cte.check is CheckFrequency.MONTHLY
    assert guide.is_manual


def test_source_kinds(tmp_path: Path) -> None:
    root = _syllabus(
        tmp_path,
        KB
        + '[[fuente]]\nid = "md"\ntipo = "markdown"\ncarpeta = "notas"\n'
        + '[[fuente]]\nid = "gh"\ntipo = "github"\nurl = "https://github.com/a/b"\n'
        + '[[fuente]]\nid = "w"\ntipo = "web"\nurl = "https://boe.es/x"\n',
    )

    kinds = [source.kind for source in load_syllabus(root).sources]

    assert kinds == [SourceKind.MARKDOWN, SourceKind.GITHUB, SourceKind.WEB]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('[[fuente]]\nid = "a"\ntipo = "pdf"\ncarpeta = "x"\n', "necesita 'archivo'"),
        ('[[fuente]]\nid = "a"\ntipo = "github"\n', "necesita 'url'"),
        (
            '[[fuente]]\nid = "a"\ntipo = "markdown"\ncarpeta = "x"\n'
            'url = "https://boe.es/a"\n',
            "no lleva 'url'",
        ),
        (
            '[[fuente]]\nid = "a"\ntipo = "pdf"\ncarpeta = "x"\narchivo = "a.pdf"\n'
            'comprobar = "mensual"\n',
            "solo se pueden comprobar",
        ),
        (
            '[[fuente]]\nid = "a"\ntipo = "web"\nurl = "https://boe.es"\n'
            'carpeta = "x"\n',
            "claves desconocidas: carpeta",
        ),
        ('[[fuente]]\nid = "a"\ntipo = "video"\n', "'tipo' debe ser uno de"),
        ('[[fuente]]\nid = "A b"\ntipo = "web"\n', "slug"),
        (
            '[[fuente]]\nid = "a"\ntipo = "pdf"\ncarpeta = "../fuera"\n'
            'archivo = "a.pdf"\n',
            "ruta relativa",
        ),
        (
            '[[fuente]]\nid = "a"\ntipo = "pdf"\ncarpeta = "x"\narchivo = "a.docx"\n',
            "nombre de PDF",
        ),
    ],
)
def test_invalid_source(tmp_path: Path, body: str, message: str) -> None:
    root = _syllabus(tmp_path, KB + body)

    with pytest.raises(ConfigError, match=message):
        load_syllabus(root)


def test_source_without_kb(tmp_path: Path) -> None:
    kb = '[[kb]]\nid = "kb-a"\nvinculante = true\nfuentes = ["cte-*"]\n'
    root = _syllabus(
        tmp_path, kb + '[[fuente]]\nid = "rebt"\ntipo = "web"\nurl = "https://boe.es"\n'
    )

    with pytest.raises(ConfigError, match="no pertenece a ninguna KB"):
        load_syllabus(root)


def test_source_in_two_kbs(tmp_path: Path) -> None:
    kb_b = '[[kb]]\nid = "kb-b"\nvinculante = false\nfuentes = ["a"]\n'
    root = _syllabus(
        tmp_path,
        KB + kb_b + '[[fuente]]\nid = "a"\ntipo = "web"\nurl = "https://boe.es"\n',
    )

    with pytest.raises(ConfigError, match="varias KB: kb-a, kb-b"):
        load_syllabus(root)


def test_pattern_without_sources_is_a_warning(tmp_path: Path) -> None:
    kb_b = '[[kb]]\nid = "kb-rebt"\nvinculante = true\nfuentes = ["rebt-*"]\n'
    kb_a = '[[kb]]\nid = "kb-a"\nvinculante = true\nfuentes = ["a"]\n'
    root = _syllabus(
        tmp_path,
        kb_a + kb_b + '[[fuente]]\nid = "a"\ntipo = "web"\nurl = "https://boe.es"\n',
    )

    assert load_syllabus(root).warnings == (
        "KB 'kb-rebt': el patrón 'rebt-*' no selecciona fuentes.",
    )


def test_duplicate_source_id(tmp_path: Path) -> None:
    source = '[[fuente]]\nid = "a"\ntipo = "web"\nurl = "https://boe.es"\n'
    root = _syllabus(tmp_path, KB + source + source)

    with pytest.raises(ConfigError, match="id de fuente repetido"):
        load_syllabus(root)


def test_invalid_domain(tmp_path: Path) -> None:
    root = tmp_path / "prueba"
    write(root / "temario.toml", HEAD + 'dominios_web = ["boe"]\n')

    with pytest.raises(ConfigError, match="dominio no válido"):
        load_syllabus(root)


def test_kb_ids_are_unique_across_syllabi(tmp_path: Path) -> None:
    _syllabus(tmp_path, KB, name="uno")
    _syllabus(tmp_path, KB, name="dos")

    with pytest.raises(ConfigError, match="'kb-a' está en los temarios 'dos' y 'uno'"):
        load_syllabi(tmp_path)


def test_load_syllabi_skips_folders_without_file(tmp_path: Path) -> None:
    _syllabus(tmp_path, "", name="uno")
    (tmp_path / "borrador").mkdir()

    syllabi, warnings = load_syllabi(tmp_path)

    assert [s.id for s in syllabi] == ["uno"]
    assert warnings == ["borrador: carpeta sin temario.toml, se ignora."]
