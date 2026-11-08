import socket

from atril import net


def test_local_url_uses_the_listening_address_or_none() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        url = f"http://localhost:{port}/api/v1/health"

        assert net.local_url(url) == f"http://127.0.0.1:{port}/api/v1/health"

    assert net.local_url(url) is None
    assert not net.is_up(url)  # sin esperar el rechazo lento de Windows
