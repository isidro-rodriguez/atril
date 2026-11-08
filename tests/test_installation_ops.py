import sys
from pathlib import Path

import pytest
from support import write, write_other_patches

from atril.config import load_station
from atril.errors import AtrilError
from atril.ops import Recorder
from atril.ops import installation as operations
from atril.patches import PATCHES

PATCH = PATCHES["paginas-citas"]


def test_patch_applies_once_and_reports_restart(station_dir: Path) -> None:
    station = load_station(station_dir)
    write(station.app_dir / PATCH.file, f"x = {{{PATCH.old}}}\n")
    write_other_patches(station.app_dir, PATCH.name)

    checked, changed = operations.patch(station, check_only=True)
    assert not changed
    assert any("pendiente" in f.message for f in checked)

    applied, changed = operations.patch(station)
    assert changed
    assert any("aplicado ahora" in f.message for f in applied)
    assert not operations.patch(station)[1]  # idempotente


def test_install_tools_needs_winget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(AtrilError, match="winget"):
        operations.install_tools(["git"], Recorder())


def test_missing_tools_uses_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        operations.shutil, "which", lambda name: None if name == "node" else "/x"
    )

    assert operations.missing_tools() == ["node"]
