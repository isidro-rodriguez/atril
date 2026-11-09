"""Versiones nuevas de atril: consulta, descarga e instalación detectada."""

import hashlib
import io
import json
import threading
from pathlib import Path

import pytest

from atril.errors import AtrilError, CancelledError
from atril.ops import Recorder, updates

INSTALLER = b"MZ instalador de prueba"


def _release_json(version: str, *, installer: bool = True, digest: str = "") -> bytes:
    assets = [{"name": f"atril-{version}-py3-none-any.whl"}]
    if installer:
        assets.append(
            {
                "name": f"atril-{version}-setup.exe",
                "browser_download_url": f"https://ejemplo/atril-{version}-setup.exe",
                "digest": digest or "sha256:" + hashlib.sha256(INSTALLER).hexdigest(),
            }
        )
    return json.dumps(
        {
            "tag_name": f"v{version}",
            "html_url": f"https://ejemplo/v{version}",
            "assets": assets,
        }
    ).encode()


def _serve(monkeypatch: pytest.MonkeyPatch, pages: dict[str, bytes]) -> None:
    def open_url(url: str, timeout: float = 300.0) -> io.BytesIO:
        if url not in pages:
            raise OSError("sin conexión")
        return io.BytesIO(pages[url])

    monkeypatch.setattr(updates.net, "open_url", open_url)


def test_check_reports_only_newer_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, {updates.LATEST_URL: _release_json("0.31.0")})

    release = updates.check("0.30.0")

    assert release is not None
    assert release.version == "0.31.0"
    assert release.page == "https://ejemplo/v0.31.0"
    assert release.installer_url == "https://ejemplo/atril-0.31.0-setup.exe"
    assert updates.check("0.31.0") is None
    assert updates.check("1.0.0") is None


def test_check_without_connection_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, {})

    with pytest.raises(AtrilError, match="última versión"):
        updates.check("0.30.0")


def test_release_without_installer_yet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _serve(monkeypatch, {updates.LATEST_URL: _release_json("0.31.0", installer=False)})

    release = updates.check("0.30.0")

    assert release is not None and release.installer_url is None
    with pytest.raises(AtrilError, match="aún no tiene instalador"):
        updates.download_installer(release, Recorder(), folder=tmp_path)


def test_download_checks_sha256(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://ejemplo/atril-0.31.0-setup.exe"
    _serve(monkeypatch, {updates.LATEST_URL: _release_json("0.31.0"), url: INSTALLER})
    release = updates.latest_release()

    installer = updates.download_installer(release, Recorder(), folder=tmp_path)

    assert installer.name == "atril-0.31.0-setup.exe"
    assert installer.read_bytes() == INSTALLER

    bad = updates.Release("0.31.0", "", url, "0" * 64)
    with pytest.raises(AtrilError, match="no coincide"):
        updates.download_installer(bad, Recorder(), folder=tmp_path / "otro")
    assert not list((tmp_path / "otro").iterdir())  # sin restos .part


def test_download_can_be_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = "https://ejemplo/atril-0.31.0-setup.exe"
    _serve(monkeypatch, {url: INSTALLER})
    cancel = threading.Event()
    cancel.set()
    release = updates.Release("0.31.0", "", url, "0" * 64)

    with pytest.raises(CancelledError):
        updates.download_installer(release, Recorder(), cancel, folder=tmp_path)
    assert not list(tmp_path.iterdir())


def test_installer_folder_detects_the_windows_installer(tmp_path: Path) -> None:
    app = tmp_path / "Atril"
    prefix = app / "herramientas" / "atril"
    prefix.mkdir(parents=True)

    assert updates.installer_folder(prefix) is None
    (app / "uv.exe").write_bytes(b"")
    (app / "unins000.exe").write_bytes(b"")
    assert updates.installer_folder(prefix) == app.resolve()
