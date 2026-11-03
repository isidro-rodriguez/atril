"""Peticiones HTTP mínimas (``urllib``) a servicios locales."""

import json
import urllib.error
import urllib.request
from typing import Any


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
