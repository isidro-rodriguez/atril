from pathlib import Path

from support import write

from atril.checks import Level
from atril.patches import PATCHES, Patch, PatchState

PATCH = Patch("demo", "Demo", "pkg/mod.py", "old()", "new()")


def test_states(tmp_path: Path) -> None:
    assert PATCH.state(tmp_path) is PatchState.NO_FILE

    write(tmp_path / "pkg/mod.py", "x = old()\n")
    assert PATCH.state(tmp_path) is PatchState.PENDING

    write(tmp_path / "pkg/mod.py", "x = new()\n")
    assert PATCH.state(tmp_path) is PatchState.APPLIED

    write(tmp_path / "pkg/mod.py", "x = other()\n")
    assert PATCH.state(tmp_path) is PatchState.CHANGED

    # Solo una aparición exacta es un estado limpio.
    for text in ("old()\nold()\n", "new()\nnew()\n", "old()\nnew()\n"):
        write(tmp_path / "pkg/mod.py", text)
        assert PATCH.state(tmp_path) is PatchState.CHANGED


def test_new_text_containing_old(tmp_path: Path) -> None:
    patch = Patch("demo", "Demo", "m.py", "f(a)", "f(a) or g()")

    write(tmp_path / "m.py", "x = f(a) or g()\n")
    assert patch.state(tmp_path) is PatchState.APPLIED
    assert patch.revert(tmp_path) is PatchState.PENDING
    assert (tmp_path / "m.py").read_text() == "x = f(a)\n"


def test_apply_is_idempotent_and_keeps_crlf(tmp_path: Path) -> None:
    file = tmp_path / "pkg" / "mod.py"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"a = 1\r\nx = old()\r\n")

    assert PATCH.apply(tmp_path) is PatchState.APPLIED
    assert PATCH.apply(tmp_path) is PatchState.APPLIED
    assert file.read_bytes() == b"a = 1\r\nx = new()\r\n"


def test_apply_does_not_touch_changed_code(tmp_path: Path) -> None:
    write(tmp_path / "pkg/mod.py", "x = other()\n")

    assert PATCH.apply(tmp_path) is PatchState.CHANGED
    assert (tmp_path / "pkg/mod.py").read_text() == "x = other()\n"


def test_registry_names_match_keys() -> None:
    assert all(name == patch.name for name, patch in PATCHES.items())
    assert "paginas-citas" in PATCHES


def test_revert(tmp_path: Path) -> None:
    write(tmp_path / "pkg/mod.py", "x = new()\n")

    assert PATCH.revert(tmp_path) is PatchState.PENDING
    assert (tmp_path / "pkg/mod.py").read_text() == "x = old()\n"
    assert PATCH.revert(tmp_path) is PatchState.PENDING


def test_no_window_patch_on_launcher_snippet(tmp_path: Path) -> None:
    patch = PATCHES["arranque-sin-ventana"]
    snippet = (
        "    if os.name == 'nt':\r\n"
        "        flags = (\r\n"
        "            subprocess.CREATE_NEW_PROCESS_GROUP\r\n"
        f"            {patch.old}\r\n"
        "        )\r\n"
    )
    (tmp_path / patch.file).parent.mkdir(parents=True)
    (tmp_path / patch.file).write_bytes(snippet.encode())

    assert patch.apply(tmp_path) is PatchState.APPLIED
    text = (tmp_path / patch.file).read_bytes().decode()
    assert "CREATE_NO_WINDOW" in text and "DETACHED_PROCESS" not in text
    assert text.count("\r\n") == 5


def test_no_window_patch_is_upstream_in_deeptutor_1_7_2(tmp_path: Path) -> None:
    from atril.ops.service import patch_finding

    patch = PATCHES["arranque-sin-ventana"]
    snippet = (  # el arreglo de DeepTutor 1.7.2 (#2421), sin el texto del parche
        "    if sys.platform == 'win32':\n"
        "        # A venv redirector's interpreter child must inherit a hidden\n"
        "        # DETACHED_PROCESS lets that child allocate a visible console\n"
        '        kwargs["creationflags"] = (\n'
        "            subprocess.CREATE_NEW_PROCESS_GROUP\n"
        "            | subprocess.CREATE_NO_WINDOW\n"
        "        )\n"
    )
    path = tmp_path / patch.file
    path.parent.mkdir(parents=True)
    path.write_text(snippet, encoding="utf-8")

    assert patch.state(tmp_path) is PatchState.UPSTREAM
    assert patch.apply(tmp_path) is PatchState.UPSTREAM
    assert patch.revert(tmp_path) is PatchState.UPSTREAM
    assert path.read_text(encoding="utf-8") == snippet  # no se toca
    assert patch_finding(patch.name, PatchState.UPSTREAM).level is Level.OK
