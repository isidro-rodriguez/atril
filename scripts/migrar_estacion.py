r"""Migra la estación anterior (scripts PowerShell) a la estructura de atril.

Estructura anterior::

    <raíz>/deeptutor_app/  lanzador/  materia_normativa/  evaluaciones/normativa/  data/

Estructura de atril::

    <raíz>/app/   data/   atril.toml   temarios/normativa/{temario.toml, prompt.md,
    espacio/, fuentes/, eval/}

Por defecto solo muestra el plan; con ``--aplicar`` lo ejecuta. No borra nada:
lo que ya no se usa va a ``<raíz>/_legado/`` y los ficheros modificados dejan una
copia ``*.antes-de-migrar``. Requiere DeepTutor parado y ninguna ventana (Explorador,
editor, terminal) abierta en esas carpetas.

Script de un solo uso para la estación de Isidro: no forma parte del paquete.

Uso (desde el repo de atril)::

    uv run python scripts/migrar_estacion.py D:\Desarrollo\DeepTutor
    uv run python scripts/migrar_estacion.py D:\Desarrollo\DeepTutor --aplicar
"""

import argparse
import json
import shutil
import socket
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from acodo.utils import get_file_hash
from rich.console import Console
from rich.markup import escape

from atril.config import load_station, load_syllabus
from atril.knowledge import IndexedSource, Ledger, ledger_path
from atril.sources import Registry, SourceRecord

console = Console(soft_wrap=True)

SYLLABUS = "normativa"
BOE = "https://www.boe.es"
CT = "https://www.codigotecnico.org/pdf/Documentos"


@dataclass(frozen=True)
class OldSource:
    """Fuente de ``descargar-normativa.ps1`` (o manual) y su sitio en atril."""

    folder: str
    stem: str
    """Prefijo del fichero antiguo (``<stem>_<AAAA-MM>.pdf``); vacío si es manual."""
    id: str
    filename: str
    url: str | None
    check: str = "mensual"
    title: str = ""


SOURCES = [
    OldSource(
        "01_edificacion_CTE",
        "CTE_RD-314-2006_consolidado",
        "cte-rd-314-2006",
        "CTE_RD-314-2006.pdf",
        f"{BOE}/buscar/pdf/2006/BOE-A-2006-5515-consolidado.pdf",
        title="RD 314/2006, Código Técnico de la Edificación (consolidado)",
    ),
    OldSource(
        "01_edificacion_CTE",
        "LOE_Ley-38-1999_consolidado",
        "loe",
        "LOE_Ley-38-1999.pdf",
        f"{BOE}/buscar/pdf/1999/BOE-A-1999-21567-consolidado.pdf",
        title="Ley 38/1999 de Ordenación de la Edificación (consolidada)",
    ),
    *[
        OldSource(
            "01_edificacion_CTE",
            f"CTE_DB-{db}",
            f"cte-db-{db.lower()}",
            f"CTE_DB-{db}.pdf",
            f"{CT}/{db.split('-')[0]}/DB{db}.pdf",
            title=f"CTE DB-{db}",
        )
        for db in (
            "SE",
            "SE-AE",
            "SE-C",
            "SE-A",
            "SE-F",
            "SE-M",
            "SI",
            "SUA",
            "HS",
            "HR",
            "HE",
        )
    ],
    *[
        OldSource(
            "01_edificacion_CTE",
            f"GUIA_CTE_DB-{db}_comentarios",
            f"guia-cte-db-{db.lower()}",
            f"GUIA_CTE_DB-{db}_comentarios.pdf",
            f"{CT}/{db}/Dcc{db}.pdf",
            title=f"CTE DB-{db} con comentarios (no vinculante)",
        )
        for db in ("SI", "SUA", "HS", "HE")
    ],
    OldSource(
        "02_estructuras",
        "CodigoEstructural_RD-470-2021",
        "codigo-estructural",
        "CodigoEstructural_RD-470-2021.pdf",
        f"{BOE}/boe/dias/2021/08/10/pdfs/BOE-A-2021-13681.pdf",
        check="nunca",
        title="Código Estructural (RD 470/2021, BOE original)",
    ),
    OldSource(
        "02_estructuras",
        "CodigoEstructural_correccion-errores-2024",
        "codigo-estructural-correccion-2024",
        "CodigoEstructural_correccion-errores-2024.pdf",
        f"{BOE}/boe/dias/2024/02/02/pdfs/BOE-A-2024-1989.pdf",
        check="nunca",
        title="Código Estructural, corrección de errores 2024",
    ),
    OldSource(
        "03_electricidad_REBT",
        "REBT_e_ITC-BT_codigo-BOE",
        "rebt",
        "REBT_e_ITC-BT.pdf",
        f"{BOE}/biblioteca_juridica/codigos/abrir_pdf.php?fich=326_Reglamento_electrotecnico"
        "_para_baja_tension_e_ITC.pdf",
        title="REBT e ITC-BT (código electrónico BOE)",
    ),
    OldSource(
        "03_electricidad_REBT",
        "",
        "guia-rebt",
        "GUIA_REBT_guia-tecnica.pdf",
        None,
        check="nunca",
        title="Guía técnica de aplicación del REBT (no vinculante)",
    ),
    OldSource(
        "04_administrativo",
        "Ley-39-2015_PACAP_consolidado",
        "ley-39-2015",
        "Ley-39-2015_PACAP.pdf",
        f"{BOE}/buscar/pdf/2015/BOE-A-2015-10565-consolidado.pdf",
        title="Ley 39/2015 del Procedimiento Administrativo Común (consolidada)",
    ),
    OldSource(
        "04_administrativo",
        "Ley-40-2015_RJSP_consolidado",
        "ley-40-2015",
        "Ley-40-2015_RJSP.pdf",
        f"{BOE}/buscar/pdf/2015/BOE-A-2015-10566-consolidado.pdf",
        title="Ley 40/2015 de Régimen Jurídico del Sector Público (consolidada)",
    ),
    OldSource(
        "05_urbanismo",
        "Estatal_TRLSRU_RDLeg-7-2015_consolidado",
        "trlsru-2015",
        "Estatal_TRLSRU_RDLeg-7-2015.pdf",
        f"{BOE}/buscar/pdf/2015/BOE-A-2015-11723-consolidado.pdf",
        title="TR Ley de Suelo y Rehabilitación Urbana (consolidado)",
    ),
    OldSource(
        "05_urbanismo",
        "Canarias_Ley-4-2017_Suelo-ENP_consolidado",
        "canarias-ley-4-2017",
        "Canarias_Ley-4-2017_Suelo-ENP.pdf",
        f"{BOE}/buscar/pdf/2017/BOE-A-2017-10295-consolidado.pdf",
        title="Ley 4/2017 del Suelo y Espacios Naturales Protegidos de Canarias",
    ),
    *[
        OldSource(
            "05_urbanismo",
            "",
            f"canarias-decreto-{n}-2018",
            f"Canarias_Decreto-{n}-2018.pdf",
            None,
            check="nunca",
            title=f"Decreto {n}/2018 (reglamento de la Ley 4/2017 de Canarias)",
        )
        for n in (181, 182, 183)
    ],
    OldSource(
        "05_urbanismo",
        "",
        "piot",
        "PIOT_Tenerife.pdf",
        None,
        check="nunca",
        title="Plan Insular de Ordenación de Tenerife",
    ),
    OldSource(
        "05_urbanismo",
        "",
        "pgo",
        "PGO_municipal.pdf",
        None,
        check="nunca",
        title="Plan General de Ordenación municipal",
    ),
    *[
        OldSource(
            "06_sistemas_gestion_ISO",
            "",
            f"iso-{n}",
            f"ISO-{n}.pdf",
            None,
            check="nunca",
            title=f"UNE-EN ISO {n} (copia propia con licencia)",
        )
        for n in (9001, 14001, 45001)
    ],
]

KBS = [
    ("norm-edificacion-cte", True, ["cte-*", "loe"], "eval/cte-v2.jsonl"),
    ("norm-edificacion-cte-guias", False, ["guia-cte-*"], None),
    ("norm-estructuras", True, ["codigo-estructural*"], None),
    ("norm-electricidad-rebt", True, ["rebt"], None),
    ("norm-electricidad-rebt-guias", False, ["guia-rebt"], None),
    ("norm-administrativo", True, ["ley-39-2015", "ley-40-2015"], None),
    ("norm-urbanismo", True, ["trlsru-2015", "canarias-*", "piot", "pgo"], None),
    ("norm-sistemas-gestion", True, ["iso-*"], None),
]

STATION_DEEPTUTOR = """[deeptutor]
repo = "https://github.com/HKUDS/DeepTutor"
rama = "dev"
python = "3.13"
puertos = { backend = 8001, frontend = 3782 }
parches = ["paginas-citas"]
paquetes = ["claude-agent-sdk>=0.2.174,<0.3"]  # LLM claude_code
busqueda = "duckduckgo"

[deeptutor.llm]
proveedor = "claude_code"
modelo = "claude-code/opus"

"""


class Plan:
    """Lista de pasos; se muestran todos y se ejecutan solo con ``--aplicar``."""

    def __init__(self, apply: bool) -> None:
        """Plan vacío; ``apply`` indica si se ejecuta."""
        self.apply = apply
        self.steps = 0

    def step(self, text: str) -> bool:
        """Anuncia un paso; devuelve si hay que ejecutarlo."""
        self.steps += 1
        mark = "[green]✓[/]" if self.apply else "[cyan]→[/]"
        console.print(f"  {mark} {escape(text)}")
        return self.apply

    def move(self, source: Path, target: Path, root: Path) -> None:
        """Mueve un fichero o carpeta (crea la carpeta de destino)."""
        if not source.exists():
            return
        if self.step(f"mover {_rel(source, root)} → {_rel(target, root)}"):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(source, target)


def _rel(path: Path, root: Path) -> str:
    """Ruta relativa a la estación, para mostrar."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _port_busy(port: int) -> bool:
    """Algo escucha en el puerto local."""
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _is_link(path: Path) -> bool:
    """Enlace simbólico o junction de Windows."""
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _old_file(folder: Path, source: OldSource) -> Path | None:
    """Fichero antiguo de una fuente (``<stem>_<AAAA-MM>.pdf``), si existe."""
    if not source.stem or not folder.is_dir():
        return None
    matches = sorted(folder.glob(f"{source.stem}_*.pdf"))
    return matches[-1] if matches else None


def check_preconditions(root: Path) -> list[str]:
    """Problemas que impiden migrar."""
    problems = []
    if not (root / "deeptutor_app").is_dir() and not (root / "app").is_dir():
        problems.append("no existe deeptutor_app ni app.")
    if not (root / "materia_normativa").is_dir():
        problems.append("no existe materia_normativa (¿ya migrada?).")
    if (root / "temarios" / SYLLABUS).exists():
        problems.append(f"ya existe temarios/{SYLLABUS}.")
    if _port_busy(8001) or _port_busy(3782):
        problems.append("DeepTutor está en marcha (puertos 8001/3782): páralo antes.")
    return problems


def migrate_app(root: Path, plan: Plan) -> None:
    """``deeptutor_app`` → ``app``; aparta el venv (sus .exe llevan rutas fijas)."""
    old, new = root / "deeptutor_app", root / "app"
    if not old.is_dir():
        return
    if _is_link(new) and plan.step(
        "quitar el enlace app → deeptutor_app (no toca el destino)"
    ):
        if new.is_symlink():
            new.unlink()
        else:
            new.rmdir()  # junction: se elimina el enlace, no su contenido
    plan.move(old, new, root)
    plan.move(new / ".venv", new / ".venv.antes-de-migrar", root)


def migrate_syllabus(root: Path, plan: Plan) -> Path:
    """``materia_normativa`` → ``temarios/normativa/espacio`` (sin lo ajeno)."""
    syllabus = root / "temarios" / SYLLABUS
    space = syllabus / "espacio"
    legacy = root / "_legado"
    plan.move(root / "materia_normativa", space, root)
    # Ya movido (o pendiente): se trabaja con la ruta de origen si aún no se ha movido.
    origin = space if plan.apply else root / "materia_normativa"

    assigned: set[Path] = set()
    for source in SOURCES:
        old = _old_file(origin / "fuentes" / source.folder, source)
        if old is not None:
            assigned.add(old)
            plan.move(old, syllabus / "fuentes" / source.folder / source.filename, root)
    for folder in (
        sorted((origin / "fuentes").glob("*")) if (origin / "fuentes").is_dir() else []
    ):
        if folder.is_dir():
            for leftover in sorted(folder.iterdir()):
                if leftover in assigned:
                    continue
                if leftover.suffix.lower() == ".pdf":
                    console.print(
                        f"  [yellow]! {escape(leftover.name)} no está en la lista: se "
                        "deja en fuentes/ y tendrás que declararlo en temario.toml.[/]"
                    )
                    target = syllabus / "fuentes" / folder.name / leftover.name
                else:
                    target = legacy / "fuentes" / folder.name / leftover.name
                plan.move(leftover, target, root)
            if plan.apply:
                (syllabus / "fuentes" / folder.name).mkdir(parents=True, exist_ok=True)
                folder.rmdir()
        else:
            plan.move(folder, legacy / "fuentes" / folder.name, root)
    if plan.apply and (origin / "fuentes").is_dir():
        (origin / "fuentes").rmdir()

    plan.move(origin / "prompt-espacio.txt", syllabus / "prompt.md", root)
    for name in ("FUENTES.md", "descargar-normativa.ps1"):
        plan.move(origin / name, legacy / "materia_normativa" / name, root)

    evaluations = root / "evaluaciones" / "normativa"
    for name in ("cte-v2.jsonl", "cte-piloto.jsonl"):
        plan.move(evaluations / name, syllabus / "eval" / name, root)
    plan.move(evaluations / "informes", syllabus / "eval" / "informes-previos", root)
    plan.move(root / "evaluaciones", legacy / "evaluaciones", root)
    plan.move(root / "lanzador", legacy / "lanzador", root)
    return syllabus


def write_temario(syllabus: Path, plan: Plan) -> None:
    """Escribe ``temario.toml`` con las fuentes y KB de la normativa."""
    if not plan.step(
        f"escribir temarios/{SYLLABUS}/temario.toml ({len(SOURCES)} fuentes)"
    ):
        return
    lines = [
        "[temario]",
        'nombre = "Normativa de construcción y gestión integrada"',
        'prompt = "prompt.md"',
        'dominios_web = ["boe.es", "codigotecnico.org", "gobiernodecanarias.org"]',
        "",
    ]
    for kb_id, binding, patterns, evaluation in KBS:
        lines += ["[[kb]]", f'id = "{kb_id}"', f"vinculante = {str(binding).lower()}"]
        lines.append("fuentes = [" + ", ".join(f'"{p}"' for p in patterns) + "]")
        if evaluation:
            lines.append(f'evaluacion = "{evaluation}"')
        lines.append("")
    for source in SOURCES:
        lines += ["[[fuente]]", f'id = "{source.id}"', 'tipo = "pdf"']
        if source.title:
            lines.append(f'titulo = "{source.title}"')
        if source.url:
            lines.append(f'url = "{source.url}"')
        lines += [f'archivo = "{source.filename}"', f'carpeta = "{source.folder}"']
        lines += [f'comprobar = "{source.check if source.url else "nunca"}"', ""]
    (syllabus / "temario.toml").write_text("\n".join(lines), encoding="utf-8")


def write_registries(root: Path, plan: Plan) -> None:
    """Registros de fuentes e indexado según lo que ya hay en disco y en las KB."""
    if not plan.step("escribir fuentes/registro.json y fuentes/indexado.json"):
        return
    syllabus = load_syllabus(root / "temarios" / SYLLABUS)
    registry = Registry(syllabus.registry_file)
    ledger = Ledger(ledger_path(syllabus))
    raw_by_kb: dict[str, dict[str, Path]] = {}
    for kb in syllabus.knowledge_bases:
        raw = root / "data" / "knowledge_bases" / kb.id / "raw"
        files = sorted(raw.glob("*.pdf")) if raw.is_dir() else []
        raw_by_kb[kb.id] = {get_file_hash(path): path for path in files}

    for source in syllabus.sources:
        path = syllabus.source_path(source)
        if path is None or not path.is_file():
            continue
        digest = get_file_hash(path)
        stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(microsecond=0)
        if source.url:
            iso = stamp.isoformat()
            registry.records[source.id] = SourceRecord(
                source.url, digest, path.stat().st_size, iso, iso
            )
        kb = syllabus.kb_of(source)
        indexed = raw_by_kb[kb.id].pop(digest, None)
        if indexed is not None:
            when = datetime.fromtimestamp(indexed.stat().st_mtime, UTC).replace(
                microsecond=0
            )
            ledger.kb(kb.id).sources[source.id] = IndexedSource(
                indexed.name, digest, when.isoformat()
            )
    # Lo que quede en raw/ sin fuente (p. ej. guías que estuvieron en la KB vinculante)
    # se anota como fuente "legado": kb reindexar lo quitará de la KB.
    for kb_id, leftovers in raw_by_kb.items():
        for digest, path in leftovers.items():
            key = "legado-" + "".join(
                c if c.isalnum() else "-" for c in path.stem.lower()
            )
            ledger.kb(kb_id).sources[key[:60]] = IndexedSource(
                path.name, digest, "previo"
            )
    registry.save()
    ledger.save()


def update_workspace(root: Path, plan: Plan) -> None:
    """Apunta el espacio «Normativa» de DT a su nueva carpeta (mismo id y ajustes)."""
    database = root / "data" / "user" / ".runtime" / "workspaces.sqlite3"
    old_path = str(root / "materia_normativa")
    new_path = str(root / "temarios" / SYLLABUS / "espacio")
    if not database.is_file():
        console.print(
            "  [yellow]! No hay workspaces.sqlite3: registra el espacio a mano.[/]"
        )
        return
    if not plan.step(f"espacio de DeepTutor: {old_path} → {new_path}"):
        return
    shutil.copy2(database, database.with_name(database.name + ".antes-de-migrar"))
    with sqlite3.connect(database) as conn:
        changed = 0
        for workspace_id, payload in conn.execute(
            "SELECT id, payload FROM workspaces"
        ).fetchall():
            row = json.loads(payload)
            if Path(row.get("path", "")) == Path(old_path):
                row["path"] = new_path
                conn.execute(
                    "UPDATE workspaces SET payload = ? WHERE id = ?",
                    (json.dumps(row, ensure_ascii=False), workspace_id),
                )
                changed += 1
    if changed != 1:
        console.print(
            f"  [yellow]! Espacios actualizados: {changed} (se esperaba 1).[/]"
        )


def update_station_file(root: Path, plan: Plan) -> None:
    """Completa ``atril.toml`` con lo de ``setup.json`` (LLM, paquetes, búsqueda)."""
    path = root / "atril.toml"
    if not path.is_file():
        console.print(
            "  [yellow]! No hay atril.toml: copia docs/ejemplos/atril.toml.[/]"
        )
        return
    text = path.read_text(encoding="utf-8")
    if "[deeptutor.llm]" in text:
        return
    if not plan.step(
        "atril.toml: añadir paquetes, búsqueda y [deeptutor.llm] de setup.json"
    ):
        return
    shutil.copy2(path, path.with_name("atril.toml.antes-de-migrar"))
    start = text.index("[deeptutor]")
    end = text.index("[ollama]")
    text = text[:start] + STATION_DEEPTUTOR + text[end:]
    text = text.replace("data\\ (DEEPTUTOR_HOME)", "data\\ (datos de DeepTutor)")
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "raiz", type=Path, help="Raíz de la estación (D:\\Desarrollo\\DeepTutor)."
    )
    parser.add_argument("--aplicar", action="store_true", help="Ejecuta el plan.")
    args = parser.parse_args(argv)
    root: Path = args.raiz.resolve()

    problems = check_preconditions(root)
    if problems:
        for problem in problems:
            console.print(f"[bold red]✗[/] {escape(problem)}")
        return 1

    plan = Plan(args.aplicar)
    title = (
        "Migración" if plan.apply else "Plan de migración (sin cambios; usa --aplicar)"
    )
    console.rule(f"[bold]{title}[/]", align="left")
    try:
        migrate_app(root, plan)
        syllabus = migrate_syllabus(root, plan)
        write_temario(syllabus, plan)
        write_registries(root, plan)
        update_workspace(root, plan)
        update_station_file(root, plan)
    except OSError as exc:
        # En Windows, lo habitual es un fichero abierto (Explorador, editor, terminal).
        console.print(
            f"\n[bold red]✗ Falló el paso {plan.steps}:[/] {escape(str(exc))}\n"
            "No se ha borrado nada: los pasos anteriores quedan hechos y lo apartado "
            "está en _legado\\. Cierra lo que tenga abiertas esas carpetas y "
            "termina los pasos que faltan a mano, o restaura el backup."
        )
        return 1

    if plan.apply:
        load_station(root)  # valida atril.toml
        console.print(
            "\n[bold green]Migración hecha.[/] Ahora: atril validar · atril instalar "
            "(recrea app\\.venv) · atril temario cobertura normativa · atril arrancar\n"
            "Cuando todo funcione, puedes borrar _legado\\, "
            "app\\.venv.antes-de-migrar y "
            "los ficheros *.antes-de-migrar."
        )
    else:
        console.print(f"\n{plan.steps} pasos. Repite con --aplicar para ejecutarlos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
