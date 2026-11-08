"""Peticiones HTTP mínimas (``urllib``): servicios locales y descargas."""

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from atril import __version__

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) atril/{__version__}"
)
"""User-Agent de las descargas: BOE y codigotecnico.org rechazan clientes genéricos."""


LOOPBACK = {
    "localhost": ("127.0.0.1", "::1"),
    "127.0.0.1": ("127.0.0.1",),
    "::1": ("::1",),
}
"""Direcciones que se prueban para cada nombre local."""

PROBE_TIMEOUT = 0.25
"""Segundos para ver si un puerto local escucha (en local responde en milisegundos)."""


def local_url(url: str) -> str | None:
    """URL con la dirección local que escucha, ``None`` si no escucha ninguna.

    En Windows, conectar a un puerto local cerrado tarda unos 2 s por dirección
    (reintenta pese al rechazo) y ``localhost`` prueba ``::1`` y ``127.0.0.1``:
    un servicio parado costaba 4 s por consulta. Se sondea el puerto con un
    tiempo corto y se usa la dirección que respondió. Las URL que no son locales
    se devuelven sin cambios.

    Examples:
        >>> local_url("https://www.boe.es/a.pdf")
        'https://www.boe.es/a.pdf'
    """
    parts = urllib.parse.urlsplit(url)
    addresses = LOOPBACK.get(parts.hostname or "")
    if addresses is None:
        return url
    port = parts.port or (443 if parts.scheme == "https" else 80)
    for address in addresses:
        try:
            with socket.create_connection((address, port), timeout=PROBE_TIMEOUT):
                pass
        except OSError:
            continue
        host = f"[{address}]" if ":" in address else address
        netloc = f"{host}:{parts.port}" if parts.port else host
        return urllib.parse.urlunsplit(parts._replace(netloc=netloc))
    return None


def is_up(url: str, timeout: float = 3.0) -> bool:
    """Indica si ``url`` responde con un código HTTP menor que 500.

    Args:
        url: Dirección a comprobar.
        timeout: Segundos de espera.

    Returns:
        ``True`` si el servidor responde (incluido un 4xx); ``False`` si no hay
        conexión, se agota el tiempo o responde con 5xx.
    """
    target = local_url(url)
    if target is None:
        return False
    try:
        with urllib.request.urlopen(target, timeout=timeout) as response:
            return response.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (urllib.error.URLError, OSError):
        return False


def get_json(url: str, timeout: float = 3.0) -> Any:
    """Descarga y decodifica una respuesta JSON.

    Raises:
        OSError: Si no hay conexión o el servidor responde con error
            (``urllib.error.URLError`` y ``HTTPError`` lo son).
        ValueError: Si la respuesta no es JSON.
    """
    target = local_url(url)
    if target is None:
        raise urllib.error.URLError(f"no escucha nada en {url}")
    with urllib.request.urlopen(target, timeout=timeout) as response:
        return json.load(response)


def open_url(url: str, timeout: float = 300.0) -> Any:
    """Abre ``url`` para descargarla con el User-Agent de atril.

    Returns:
        La respuesta de ``urllib`` (iterable por bloques con ``read``; cabeceras
        en ``headers``). Úsala con ``with``.

    Raises:
        OSError: Si no hay conexión o el servidor responde con error.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def request_json(
    url: str,
    method: str = "GET",
    form: dict[str, str] | None = None,
    payload: Any = None,
    timeout: float = 60.0,
) -> Any:
    """Petición HTTP que devuelve JSON (formulario o cuerpo JSON opcionales).

    Raises:
        HttpError: Si el servidor responde con error (incluye su ``detail``).
        OSError: Si no hay conexión.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    target = local_url(url)
    if target is None:
        raise urllib.error.URLError(f"no escucha nada en {url}")
    request = urllib.request.Request(target, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise HttpError(exc.code, _detail(exc.read())) from exc
    return json.loads(body) if body else None


class HttpError(OSError):
    """Respuesta HTTP de error, con el detalle que devuelve el servidor."""

    def __init__(self, status: int, detail: str) -> None:
        """Guarda el código y el detalle."""
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def _detail(body: bytes) -> str:
    """Campo ``detail`` de una respuesta de error de FastAPI, o el texto tal cual."""
    text = body.decode("utf-8", errors="replace").strip()
    try:
        detail = json.loads(text).get("detail", text)
    except (ValueError, AttributeError):
        return text[:300]
    return str(detail)[:300]
