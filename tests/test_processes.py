import os
import socket
from pathlib import Path

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
