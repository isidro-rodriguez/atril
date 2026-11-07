import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from support import write

from atril import sources
from atril.config import StateFileError, load_syllabus
from atril.config.syllabus import Syllabus
from atril.sources import (
    DownloadError,
    Outcome,
    Registry,
    SourceManager,
    SourceRecord,
    download,
    is_due,
)

PDF_V1 = b"%PDF-1.7 version uno"
PDF_V2 = b"%PDF-1.7 version dos, con cambios"


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes) -> None:
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


class FakeWeb:
    """Sustituye a net.open_url: sirve un contenido por URL o lanza un error."""

    def __init__(self) -> None:
        self.pages: dict[str, bytes | Exception] = {}
        self.requests: list[str] = []

    def open_url(self, url: str, timeout: float = 300.0) -> FakeResponse:
        self.requests.append(url)
        page = self.pages.get(url, OSError("HTTP Error 404: Not Found"))
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> FakeWeb:
    fake = FakeWeb()
    monkeypatch.setattr(sources.net, "open_url", fake.open_url)
    return fake


@pytest.fixture
def syllabus(station_dir: Path) -> Syllabus:
    return load_syllabus(station_dir / "temarios" / "normativa")


def _source(syllabus: Syllabus, source_id: str):
    return next(s for s in syllabus.sources if s.id == source_id)


def test_download_writes_pdf_and_reports_progress(tmp_path: Path, web: FakeWeb) -> None:
    web.pages["https://x.es/a.pdf"] = PDF_V1
    seen: list[tuple[int, int | None]] = []

    sha, size = download(
        "https://x.es/a.pdf", tmp_path / "a.pdf", lambda d, t: seen.append((d, t))
    )

    assert (tmp_path / "a.pdf").read_bytes() == PDF_V1
    assert size == len(PDF_V1)
    assert len(sha) == 64
    assert seen[-1] == (len(PDF_V1), len(PDF_V1))


@pytest.mark.parametrize(
    ("page", "message"),
    [
        (b"<html>Error 500</html>", "no es un PDF"),
        (b"", "vacía"),
        (OSError("timed out"), "no se puede descargar"),
    ],
)
def test_download_rejects_bad_responses(
    tmp_path: Path, web: FakeWeb, page: bytes | Exception, message: str
) -> None:
    web.pages["https://x.es/a.pdf"] = page

    with pytest.raises(DownloadError, match=message):
        download("https://x.es/a.pdf", tmp_path / "a.pdf")
    assert list(tmp_path.iterdir()) == []  # ni el PDF ni el .part


def test_fetch_outcomes(syllabus: Syllabus, web: FakeWeb) -> None:
    cte = _source(syllabus, "cte-db-si")
    web.pages[cte.url or ""] = PDF_V1
    manager = SourceManager(syllabus)

    assert manager.fetch(cte).outcome is Outcome.DOWNLOADED
    assert manager.fetch(cte).outcome is Outcome.PRESENT
    assert manager.fetch(_source(syllabus, "loe")).outcome is Outcome.FAILED

    manual = manager.fetch(_source(syllabus, "guia-cte-si"))
    assert manual.outcome is Outcome.MANUAL
    assert "02_guias_CTE" in manual.detail

    record = manager.registry.get("cte-db-si")
    assert record is not None and record.size == len(PDF_V1)
    assert (syllabus.sources_dir / "01_edificacion_CTE" / "DBSI.pdf").is_file()


def test_fetch_registers_preexisting_file(syllabus: Syllabus, web: FakeWeb) -> None:
    cte = _source(syllabus, "cte-db-si")
    path = syllabus.source_path(cte)
    assert path is not None
    path.parent.mkdir(parents=True)
    path.write_bytes(PDF_V1)
    manager = SourceManager(syllabus)

    assert manager.fetch(cte).outcome is Outcome.PRESENT
    assert manager.registry.get("cte-db-si") is not None
    assert web.requests == []


def test_check_unchanged_then_updated(syllabus: Syllabus, web: FakeWeb) -> None:
    cte = _source(syllabus, "cte-db-si")
    url = cte.url or ""
    web.pages[url] = PDF_V1
    manager = SourceManager(syllabus)
    manager.fetch(cte)
    first = manager.registry.get(cte.id)
    assert first is not None

    assert manager.check(cte).outcome is Outcome.UNCHANGED

    web.pages[url] = PDF_V2
    result = manager.check(cte)

    assert result.outcome is Outcome.UPDATED
    path = syllabus.source_path(cte)
    assert path is not None and path.read_bytes() == PDF_V2
    old = (
        syllabus.history_dir
        / "01_edificacion_CTE"
        / f"DBSI.{first.downloaded_at[:10]}.pdf"
    )
    assert old.read_bytes() == PDF_V1
    assert "historico" in result.detail
    assert not list(path.parent.glob("*.nuevo"))


def test_check_failure_keeps_current_file(syllabus: Syllabus, web: FakeWeb) -> None:
    cte = _source(syllabus, "cte-db-si")
    web.pages[cte.url or ""] = PDF_V1
    manager = SourceManager(syllabus)
    manager.fetch(cte)

    web.pages[cte.url or ""] = b"<html>mantenimiento</html>"

    assert manager.check(cte).outcome is Outcome.FAILED
    path = syllabus.source_path(cte)
    assert path is not None and path.read_bytes() == PDF_V1


def test_registry_roundtrip_and_local_state(syllabus: Syllabus, web: FakeWeb) -> None:
    cte = _source(syllabus, "cte-db-si")
    web.pages[cte.url or ""] = PDF_V1
    manager = SourceManager(syllabus)
    manager.fetch(cte)
    manager.registry.save()

    reloaded = SourceManager(syllabus)
    assert reloaded.registry.get(cte.id) == manager.registry.get(cte.id)
    assert reloaded.local_state(cte) == "presente"
    assert reloaded.local_state(_source(syllabus, "loe")) == "falta"

    path = syllabus.source_path(cte)
    assert path is not None
    path.write_bytes(b"%PDF editado a mano")
    assert reloaded.local_state(cte) == "modificada"


def test_markdown_and_remote_sources(tmp_path: Path) -> None:
    root = tmp_path / "t"
    write(
        root / "temario.toml",
        '[temario]\nnombre = "T"\n'
        '[[kb]]\nid = "kb"\nvinculante = false\nfuentes = ["*"]\n'
        '[[fuente]]\nid = "notas"\ntipo = "markdown"\ncarpeta = "notas"\n'
        '[[fuente]]\nid = "web"\ntipo = "web"\nurl = "https://boe.es"\n',
    )
    syllabus = load_syllabus(root)
    manager = SourceManager(syllabus)
    notes, remote = syllabus.sources

    assert manager.fetch(notes).outcome is Outcome.MISSING
    write(syllabus.sources_dir / "notas" / "a.md", "# Hola")
    assert manager.fetch(notes).outcome is Outcome.PRESENT
    assert manager.fetch(remote).outcome is Outcome.REMOTE


def test_is_due_needs_url_and_frequency(syllabus: Syllabus) -> None:
    now = datetime(2026, 11, 3, tzinfo=UTC)
    record = SourceRecord(
        "u", "h", 1, "2026-10-01T00:00:00+00:00", "2026-10-01T00:00:00+00:00"
    )

    assert is_due(_source(syllabus, "cte-db-si"), None, now)
    assert is_due(_source(syllabus, "cte-db-si"), record, now)
    assert not is_due(_source(syllabus, "guia-cte-si"), None, now)


def test_registry_file_is_sorted_text(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "registro.json")
    for key in ("b", "a"):
        registry.records[key] = SourceRecord("u", "h", 1, "d", "c")
    registry.save()

    text = (tmp_path / "registro.json").read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')
    assert text.endswith("\n")


@pytest.mark.parametrize(
    "text", ["{roto", '{"fuentes": []}', '{"fuentes": {"a": {"otra": 1}}}']
)
def test_damaged_registry_is_never_overwritten(tmp_path: Path, text: str) -> None:
    path = write(tmp_path / "registro.json", text)

    with pytest.raises(StateFileError, match="no lo sobrescribe"):
        Registry(path)
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    "text",
    [
        '{"version": 1}',
        '{"fuentes": {}}',
        '{"version": 2, "fuentes": {}}',
        '{"version": 1, "fuentes": {}, "extra": 1}',
        '{"version": 1, "fuentes": {"a": {"url": "", "sha256": "", "size": "5", '
        '"downloaded_at": "", "checked_at": ""}}}',
        '{"version": 1, "fuentes": {"a": {"url": "", "sha256": "", "size": true, '
        '"downloaded_at": "", "checked_at": ""}}}',
    ],
)
def test_registry_is_strict(tmp_path: Path, text: str) -> None:
    path = write(tmp_path / "registro.json", text)

    with pytest.raises(StateFileError):
        Registry(path)
