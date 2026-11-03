import os
import socket
from pathlib import Path

import pytest

from atril.processes import PortOwner, port_owners


def test_port_owners_finds_listening_socket() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]

        owners = port_owners([port])

    assert [(o.port, o.pid) for o in owners] == [(port, os.getpid())]


def test_belongs_to_ignores_case_and_separators() -> None:
    owner = PortOwner(3782, 1, "node.exe", r"d:\desarrollo\deeptutor\app\web\next")

    assert owner.belongs_to(Path("D:/Desarrollo/DeepTutor"))
    assert not owner.belongs_to(Path("D:/Desarrollo/Otra"))


@pytest.mark.parametrize(
    ("root", "args", "expected"),
    [
        (
            "D:/Desarrollo/DeepTutor",
            [r"D:\Desarrollo\DeepTutor\app\.venv\python.exe"],
            True,
        ),
        (
            "D:/Desarrollo/DeepTutor",
            [r"D:\Desarrollo\DeepTutorBackup\app\python.exe"],
            False,
        ),
        (
            "D:/Desarrollo/DeepTutor",
            [r"D:\Desarrollo\DeepTutor.previo-1\app\node.exe"],
            False,
        ),
        ("D:/Desarrollo/DeepTutor", ["node", r"--home=D:\Desarrollo\DeepTutor"], True),
        (
            "D:/Desarrollo/DeepTutor",
            ["python", '"d:\\desarrollo\\deeptutor\\app\\x.py"'],
            True,
        ),
        ("/home/u/dt", ["/home/u/dt/app/.venv/bin/python"], True),
        ("/home/u/dt", ["/home/u/dt-backup/app/.venv/bin/python"], False),
        ("/home/u/dt", ["/home/u/dt"], True),
    ],
)
def test_belongs_to_compares_paths_not_text(
    root: str, args: list[str], expected: bool
) -> None:
    owner = PortOwner(8001, 1, "p", " ".join(args), tuple(args))

    assert owner.belongs_to(Path(root)) is expected


def test_lower_priority_of_child_process() -> None:
    import subprocess
    import sys

    import psutil

    from atril.processes import lower_priority

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        before = psutil.Process(child.pid).nice()
        assert lower_priority(child.pid)
        after = psutil.Process(child.pid).nice()
        if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
            assert after == psutil.BELOW_NORMAL_PRIORITY_CLASS
        else:
            assert after > before
    finally:
        child.kill()
        child.wait()


def test_lower_priority_of_missing_process() -> None:
    from atril.processes import lower_priority

    assert lower_priority(2**22 + 12345) is False
