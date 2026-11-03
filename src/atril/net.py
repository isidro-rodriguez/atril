"""Peticiones HTTP mínimas (``urllib``): servicios locales y descargas."""

import json
import urllib.error
import urllib.request
from typing import Any

from atril import __version__

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) atril/{__version__}"
)
"""User-Agent de las descargas: BOE y codigotecnico.org rechazan clientes genéricos."""


def is_up(url: str, timeout: float = 3.0) -> bool:
    """Indica si ``url`` responde con un código HTTP menor que 500.

    Args:
        url: Dirección a comprobar.
        timeout: Segundos de espera.

    Returns:
        ``True`` si el servidor responde (incluido un 4xx); ``False`` si no hay
        conexión, se agota el tiempo o responde con 5xx.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
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
    with urllib.request.urlopen(url, timeout=timeout) as response:
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
