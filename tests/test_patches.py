from pathlib import Path

from support import write

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
