"""Comandos de instalación: ``atril instalar`` y ``atril actualizar``.

La lógica está en :mod:`atril.ops.installation`; aquí solo se traducen las
opciones y se muestra el resultado.
"""

from typing import Annotated

import typer

from atril.checks import info
from atril.commands._common import fail_error, get_station, reporter, show, success
from atril.errors import AtrilError
from atril.ops import installation as operations

NoDocling = Annotated[
    bool,
    typer.Option(
        "--sin-docling", help="No instala el parser Docling (descarga grande, PyTorch)."
    ),
]


def install_command(ctx: typer.Context, no_docling: NoDocling = False) -> None:
    """Instala DeepTutor en [bold]app/[/] o completa la instalación (re-ejecutable).

    Clona la rama configurada, crea el entorno de Python, instala el frontend,
    descarga el modelo de embedding, aplica la configuración de atril.toml y los
    parches, y termina con el diagnóstico de DeepTutor.
    """
    try:
        operations.install_deeptutor(get_station(ctx), reporter, docling=not no_docling)
    except AtrilError as exc:
        fail_error(exc)
    success("DeepTutor instalado. Arráncalo con: atril arrancar")


def update_command(
    ctx: typer.Context,
    no_docling: NoDocling = False,
    no_restart: Annotated[
        bool,
        typer.Option(
            "--sin-arrancar", help="No vuelve a arrancar DeepTutor al terminar."
        ),
    ] = False,
    commit: Annotated[
        str | None,
        typer.Option(
            "--commit",
            help="Va a este commit (hash completo): vuelta atrás de DeepTutor.",
        ),
    ] = None,
) -> None:
    """Actualiza DeepTutor a la última versión de su rama y reaplica los parches.

    Con [bold]--commit[/] va a ese commit en lugar de a la punta de la rama, p. ej.
    para volver a la versión anterior si la nueva da problemas: el comando muestra
    el hash de la que había.

    Para DeepTutor si está en marcha, comprueba que [bold]app/[/] sigue el repo y la
    rama de atril.toml, deshace los parches, trae la rama, reinstala dependencias
    (el frontend solo si cambia su lockfile), reaplica la configuración y los
    parches, y termina con el diagnóstico.
    """
    try:
        result = operations.update_deeptutor(
            get_station(ctx),
            reporter,
            docling=not no_docling,
            restart=not no_restart,
            commit=commit,
        )
    except AtrilError as exc:
        fail_error(exc)
    if result.changed:
        show([info(f"Para volver atrás: atril actualizar --commit {result.previous}")])
    success("DeepTutor actualizado.")
