"""Admit requests only to the bundled studio's local HTTP listener."""

import re

from fastapi import Request

LOOPBACK_HOSTS = frozenset(("127.0.0.1", "localhost", "::1"))
MUTATING_METHODS = frozenset(("POST", "PUT", "PATCH", "DELETE"))
_AUTHORITY = re.compile(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::([0-9]+))?", re.ASCII | re.IGNORECASE)


def _authority_port(authority: str) -> int | None:
    """Parse the entire supported authority, without URL-parser normalization."""
    match = _AUTHORITY.fullmatch(authority)
    if match is None:
        return None
    digits = (match[1] or "80").lstrip("0")
    if not digits or len(digits) > 5:
        return None
    port = int(digits)
    return port if port <= 65535 else None


def local_request_error(request: Request) -> str | None:
    """Validate raw headers against the trusted ASGI socket, before any effects."""
    server = request.scope.get("server")
    if (
        server is None
        or server[0].lower() not in LOOPBACK_HOSTS
        or server[1] is None
        or not 1 <= server[1] <= 65535
        or request.scope["scheme"] != "http"
    ):
        return "The bundled studio requires a local HTTP listener."
    hosts = request.headers.getlist("host")
    if len(hosts) != 1 or _authority_port(hosts[0]) != server[1]:
        return "Requests must address the local studio listener with one loopback Host header."
    if request.method not in MUTATING_METHODS:
        return None
    origins = request.headers.getlist("origin")
    if not origins:
        return None
    if len(origins) != 1 or not origins[0].startswith("http://"):
        return "Mutating browser requests must originate from the local studio."
    if _authority_port(origins[0][len("http://") :]) != server[1]:
        return "Mutating browser requests must originate from the local studio."
    return None
