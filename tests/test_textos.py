"""Los textos que ve el alumno en la ventana no mencionan comandos de la consola."""

import ast
import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "atril"

OPTIONS = sorted(
    {
        match
        for path in (SRC / "commands").glob("*.py")
        for match in re.findall(r'"(--[a-z][a-z-]+)', path.read_text(encoding="utf-8"))
    }
)
"""Opciones de la consola de atril (``--nueva-ruta``, ``--sin-docling``...)."""

CLI = re.compile(
    r"\batril (kb|fuentes|backup|parches|parar|arrancar|instalar|actualizar|estado|"
    r"restaurar|temario|evaluar|config|ollama|herramientas)\b|"
    + "|".join(re.escape(option) + r"\b" for option in OPTIONS)
)
"""Un comando o una opción de la consola de atril."""


def _strings(path: Path) -> list[tuple[int, str]]:
    """Textos literales del módulo, sin docstrings (de módulo, clase, función o
    atributo)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_messages_shared_with_the_window_do_not_mention_cli_commands() -> None:
    modules = [
        path
        for path in SRC.rglob("*.py")
        if "commands" not in path.parts and path.name != "main.py"
    ]
    found = [
        f"{path.relative_to(SRC)}:{line}: {text!r}"
        for path in modules
        for line, text in _strings(path)
        if CLI.search(text) and not text.startswith("--")  # argumento de un programa
    ]
    assert found == []


def test_window_texts_do_not_use_semicolons() -> None:
    found = [
        f"{path.name}:{line}: {text!r}"
        for path in (SRC / "gui").glob("*.py")
        for line, text in _strings(path)
        if ";" in text
    ]
    assert found == []
