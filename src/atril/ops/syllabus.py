"""Temarios: crear uno nuevo y añadirle fuentes.

``temario.toml`` se edita con ``tomlkit``, que conserva comentarios y orden. El
resultado se valida con :func:`atril.config.load_syllabus` antes de sustituir el
fichero, y se escribe primero como ``.nuevo``: un error no deja nada a medias.
"""

import dataclasses
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import tomlkit
from acodo.utils import parse_slug, valid_filename, valid_slug
from tomlkit.items import AoT, Array, Table

from atril.config import ConfigError, Syllabus, load_syllabi, load_syllabus
from atril.config.station import Station
from atril.config.syllabus import SYLLABUS_FILE, KnowledgeBase, Source
from atril.errors import AtrilError

PDF_HEADER = b"%PDF-"
"""Cabecera de un PDF válido."""

PROMPT_TEMPLATE = """\
# {name}

Responde a partir de las bases de conocimiento de este temario y cita el documento y la
página de donde sale cada dato. Si algo no está en ellas, dilo claramente.
"""
"""``prompt.md`` inicial de un temario nuevo."""


def create(station: Station, name: str, syllabus_id: str | None = None) -> Syllabus:
    """Crea ``temarios/<id>/`` con ``temario.toml``, ``prompt.md`` y ``fuentes/``.

    El temario empieza con una sola KB, con el mismo id, que recoge todas sus
    fuentes (``fuentes = ["*"]``).

    Args:
        station: Estación donde se crea.
        name: Nombre visible del temario.
        syllabus_id: Id (slug); por defecto, se deriva de ``name``.

    Returns:
        El temario creado y validado.

    Raises:
        AtrilError: Si el id no es válido, ya existe un temario o una KB con ese id.

    Examples:
        ``create(station, "Matemáticas II")`` crea ``temarios/matematicas-ii/``.
    """
    name = name.strip()
    if not name:
        raise AtrilError("el temario necesita un nombre.")
    new_id = syllabus_id or parse_slug(name)
    if not valid_slug(new_id):
        raise AtrilError(
            f"id de temario no válido: {new_id!r} (minúsculas, cifras y guiones)."
        )
    root = station.syllabi_dir / new_id
    if root.exists():
        raise AtrilError(f"ya existe el temario {new_id!r} ({root}).")
    syllabi, _ = load_syllabi(station.syllabi_dir)
    for other in syllabi:
        if any(kb.id == new_id for kb in other.knowledge_bases):
            raise AtrilError(
                f"ya hay una KB {new_id!r} en el temario {other.id!r}; "
                "elige otro id para el temario."
            )

    try:
        (root / "fuentes").mkdir(parents=True)
        (root / SYLLABUS_FILE).write_text(_new_syllabus(name, new_id), encoding="utf-8")
        (root / "prompt.md").write_text(
            PROMPT_TEMPLATE.format(name=name), encoding="utf-8"
        )
        return load_syllabus(root)
    except (OSError, ConfigError):
        shutil.rmtree(root, ignore_errors=True)
        raise


def add_source(
    syllabus: Syllabus,
    origin: str,
    *,
    source_id: str | None = None,
    title: str | None = None,
    kb_id: str | None = None,
) -> Source:
    """Añade una fuente PDF al temario: un fichero local (se copia) o una URL.

    El fichero se copia a ``fuentes/<kb>/`` y queda como fuente manual (sin
    ``url``); una URL se declara y se descarga después (``atril fuentes
    descargar``). Si la KB no selecciona ya el id nuevo, se añade a su lista
    ``fuentes``.

    Args:
        syllabus: Temario al que se añade.
        origin: Ruta de un PDF o URL ``http(s)://``.
        source_id: Id de la fuente; por defecto, del título o del nombre del fichero.
        title: Título visible.
        kb_id: KB de destino; obligatoria si el temario tiene varias.

    Returns:
        La fuente añadida, ya validada.

    Raises:
        AtrilError: Si el fichero no es un PDF, el id está repetido o la KB no
            existe o es ambigua.
    """
    syllabus = load_syllabus(
        syllabus.root
    )  # el objeto puede ser de antes de otra fuente
    is_url = origin.startswith(("http://", "https://"))
    local = None if is_url else Path(origin.strip().strip('"')).expanduser()
    if local is None:
        original = PurePosixPath(urlsplit(origin).path).name
    else:
        _check_pdf(local)
        original = local.name
    kb = _target_kb(syllabus, kb_id)
    new_id = _source_id(syllabus, source_id, title or Path(original).stem)
    filename = original if _is_pdf_name(original) else f"{new_id}.pdf"
    target = syllabus.sources_dir / kb.id / filename
    if local is not None and target.exists():
        raise AtrilError(f"ya existe {target}; cambia el nombre del fichero.")

    entry = tomlkit.table()
    entry["id"] = new_id
    entry["tipo"] = "pdf"
    if title:
        entry["titulo"] = title
    if is_url:
        entry["url"] = origin
    entry["carpeta"] = kb.id
    if local is not None or filename != original:
        entry["archivo"] = filename
    text = _with_source(syllabus, entry, kb, new_id)
    updated = _validate(syllabus, text)

    copied = None
    if local is not None:
        copied = _copy(local, target)
    try:
        _replace(syllabus.root / SYLLABUS_FILE, text)
    except OSError as exc:
        if copied:
            copied.unlink(missing_ok=True)
        raise AtrilError(f"no se puede escribir {SYLLABUS_FILE}: {exc}") from exc
    return next(source for source in updated.sources if source.id == new_id)


def _new_syllabus(name: str, syllabus_id: str) -> str:
    """Texto de ``temario.toml`` para un temario nuevo."""
    doc = tomlkit.document()
    doc.add(tomlkit.comment("temario.toml (referencia: docs/esquemas.md de atril)."))
    head = tomlkit.table()
    head["nombre"] = name
    doc["temario"] = head
    kb = tomlkit.table()
    kb["id"] = syllabus_id
    kb["vinculante"] = False
    kb["fuentes"] = ["*"]
    kb["descripcion"] = name
    kbs = tomlkit.aot()
    kbs.append(kb)
    doc["kb"] = kbs
    return tomlkit.dumps(doc)


def _check_pdf(path: Path) -> None:
    """El fichero existe y empieza por la cabecera de PDF."""
    try:
        with path.open("rb") as file:
            header = file.read(len(PDF_HEADER))
    except OSError as exc:
        raise AtrilError(f"no se puede leer {path}: {exc}") from exc
    if header != PDF_HEADER:
        raise AtrilError(f"{path} no es un PDF; solo se admiten fuentes PDF.")


def _is_pdf_name(name: str) -> bool:
    """Nombre de fichero válido terminado en ``.pdf``."""
    return valid_filename(name) and name.lower().endswith(".pdf")


def _target_kb(syllabus: Syllabus, kb_id: str | None) -> KnowledgeBase:
    """KB de destino: la indicada o la única del temario."""
    kbs = syllabus.knowledge_bases
    if kb_id is not None:
        for kb in kbs:
            if kb.id == kb_id:
                return kb
        raise AtrilError(f"el temario {syllabus.id!r} no tiene la KB {kb_id!r}.")
    if len(kbs) == 1:
        return kbs[0]
    names = ", ".join(kb.id for kb in kbs) or "ninguna"
    raise AtrilError(f"indica la KB de la fuente (el temario tiene: {names}).")


def _source_id(syllabus: Syllabus, wanted: str | None, text: str) -> str:
    """Id nuevo: el pedido (único) o derivado de ``text`` (``-2``... si se repite)."""
    taken = {source.id for source in syllabus.sources}
    if wanted is not None:
        if not valid_slug(wanted):
            raise AtrilError(f"id de fuente no válido: {wanted!r}.")
        if wanted in taken:
            raise AtrilError(f"ya hay una fuente {wanted!r} en {syllabus.id!r}.")
        return wanted
    base = parse_slug(text) or "fuente"
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}-{number}", number + 1
    return candidate


def _with_source(
    syllabus: Syllabus, entry: Table, kb: KnowledgeBase, source_id: str
) -> str:
    """``temario.toml`` con la fuente añadida (y su id en la KB si hace falta)."""
    path = syllabus.root / SYLLABUS_FILE
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    if not kb.matches(source_id):
        for table in doc.get("kb", []):
            if table.get("id") == kb.id:
                patterns = table["fuentes"]
                if not isinstance(patterns, Array):
                    raise AtrilError(
                        f"{path}: 'fuentes' de la KB {kb.id!r} no es una lista."
                    )
                patterns.append(source_id)
    sources = doc.get("fuente")
    if sources is None:
        sources = tomlkit.aot()
        doc["fuente"] = sources
    if not isinstance(sources, AoT):
        raise AtrilError(f"{path}: 'fuente' debe declararse como [[fuente]].")
    sources.append(entry)
    return tomlkit.dumps(doc)


def _validate(syllabus: Syllabus, text: str) -> Syllabus:
    """Valida el texto nuevo en una copia aparte, sin tocar el temario."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / syllabus.id
        root.mkdir()
        (root / SYLLABUS_FILE).write_text(text, encoding="utf-8")
        try:
            checked = load_syllabus(root)
        except ConfigError as exc:
            raise AtrilError(f"la fuente no encaja en el temario: {exc}") from exc
    return dataclasses.replace(checked, root=syllabus.root)


def _copy(source: Path, target: Path) -> Path:
    """Copia el PDF a la carpeta de fuentes (``.nuevo`` y renombrado)."""
    partial = target.with_name(target.name + ".nuevo")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, partial)
        partial.replace(target)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise AtrilError(f"no se puede copiar {source} a {target}: {exc}") from exc
    return target


def _replace(path: Path, text: str) -> None:
    """Sustituye ``path`` por ``text`` de forma atómica."""
    partial = path.with_name(path.name + ".nuevo")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)
