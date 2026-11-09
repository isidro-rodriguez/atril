"""Pruebas acotadas del generador de capturas (``scripts/capturas.py``).

La prueba de integración es su ejecución real en Windows en cada publicación;
aquí solo se cubren la validación, el aislamiento y el fallo sin publicar.
"""

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("tkinter")  # el script importa la ventana
Image = pytest.importorskip("PIL.Image")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "capturas.py"


@pytest.fixture(scope="module")
def capturas() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capturas", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shot(path: Path, size: tuple[int, int] = (1024, 700)) -> Path:
    """PNG con ruido (no comprime): como una captura real, por encima del mínimo."""
    Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)).save(path)
    return path


def _six(capturas: ModuleType, folder: Path) -> Path:
    folder.mkdir(exist_ok=True)
    for name in capturas.SHOTS:
        _shot(folder / f"{name}.png")
    return folder


def test_validate_accepts_the_six_expected_shots(
    capturas: ModuleType, tmp_path: Path
) -> None:
    capturas.validate(_six(capturas, tmp_path / "ok"))


@pytest.mark.parametrize("fault", ["falta", "sobra", "tamano", "rota", "vacia"])
def test_validate_rejects_incomplete_or_invalid_shots(
    capturas: ModuleType, tmp_path: Path, fault: str
) -> None:
    folder = _six(capturas, tmp_path / fault)
    inicio = folder / "inicio.png"
    match fault:
        case "falta":
            inicio.unlink()
        case "sobra":
            _shot(folder / "vieja.png")
        case "tamano":
            _shot(inicio, (1024, 600))
        case "rota":
            inicio.write_bytes(inicio.read_bytes()[:40_000])  # cortada a medias
        case "vacia":
            Image.new("RGB", (1024, 700), "white").save(inicio)  # pesa muy poco
    with pytest.raises((capturas.CaptureError, OSError, SyntaxError)):
        capturas.validate(folder)


def test_save_rejects_a_partly_painted_window(
    capturas: ModuleType, tmp_path: Path
) -> None:
    image = Image.new("RGB", (1024, 700), "white")
    image.paste((0, 0, 0), (900, 600, 1024, 700))  # esquina sin pintar
    with pytest.raises(capturas.CaptureError):
        capturas._save(image, tmp_path / "inicio.png", "inicio")
    assert not (tmp_path / "inicio.png").exists()


def test_workspace_is_temporary_and_removed_even_on_error(
    capturas: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError), capturas.workspace() as (root, copies, work):
        assert copies.is_dir() and root.parent == work and copies.is_relative_to(work)
        raise RuntimeError("fallo a mitad")
    assert not work.exists()


def test_workspace_refuses_existing_ci_folders_without_touching_them(
    capturas: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capturas.sys, "platform", "win32")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(capturas.Path, "exists", lambda self: True)
    removed: list[Path] = []
    monkeypatch.setattr(
        capturas.shutil, "rmtree", lambda path, **_: removed.append(path)
    )
    with pytest.raises(capturas.CaptureError, match="ya existe"), capturas.workspace():
        pass  # pragma: no cover - no llega
    # Solo se borra su propia carpeta temporal, nunca D:\Estudio ni D:\Copias.
    assert all(Path(path).name.startswith("atril-capturas-") for path in removed)


@pytest.mark.parametrize("fault", ["captura", "imagenes"])
def test_main_fails_and_keeps_published_shots(
    capturas: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    out = _six(capturas, tmp_path / "publicadas")
    before = {path.name: path.read_bytes() for path in out.iterdir()}

    def capture(window: object, shots: Path) -> None:
        if fault == "captura":
            raise capturas.CaptureError("«Backups» no ha terminado de cargar.")
        _shot(shots / "inicio.png")  # termina, pero incompleta

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(capturas, "check_version", lambda: None)
    monkeypatch.setattr(capturas, "prepare", lambda *args: None)
    monkeypatch.setattr(capturas, "open_window", lambda root: None)
    monkeypatch.setattr(capturas, "capture", capture)
    monkeypatch.setattr(sys, "argv", ["capturas.py", str(out)])

    assert capturas.main() == 1
    assert {path.name: path.read_bytes() for path in out.iterdir()} == before
