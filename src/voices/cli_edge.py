"""Read-only CLI probe for the local browser edge."""

import json
from typing import Annotated

import httpx
import typer

from voices.cli_json import context_from_typer, emit_json, require_json_readable_payload, run_cli_action
from voices.domain.errors import InvalidInputError

edge_app = typer.Typer(help="Read from a running loopback studio edge.")


def _edge_url(base_url: str, path: str) -> str:
    """Build one local edge URL from a base URL and request path."""
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}"


@edge_app.command("get")
def get_edge(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="Edge API path, for example /api/voices.")],
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="Loopback studio base URL."),
    ] = "http://127.0.0.1:8765",
    timeout: Annotated[float, typer.Option("--timeout", help="Request timeout in seconds.")] = 5.0,
) -> None:
    """Run one read-only GET request against the local studio edge."""
    context = context_from_typer(ctx)

    def run() -> None:
        url = _edge_url(base_url, path)
        try:
            response = httpx.get(url, timeout=timeout)
        except httpx.HTTPError as exc:
            raise InvalidInputError(f"Edge GET failed: {exc}") from exc
        try:
            parsed: object = response.json()
        except json.JSONDecodeError as exc:
            raise InvalidInputError("Edge GET did not return JSON.") from exc
        payload: dict[str, object] = {
            "status": response.status_code,
            "url": url,
            "body": require_json_readable_payload(parsed),
        }
        emit_json(payload)

    run_cli_action(context, run)
