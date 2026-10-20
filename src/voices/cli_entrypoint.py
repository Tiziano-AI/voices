"""Console-script entrypoint for the voices CLI."""

import sys

import typer

from voices.cli import app
from voices.cli_json import emit_json


def _argv_requests_json(arguments: list[str]) -> bool:
    """Return whether a raw CLI argv vector requested the global JSON mode."""
    return "--json" in arguments


def _emit_typer_json_error(error: typer.TyperException) -> None:
    """Emit one Typer usage error through the CLI JSON envelope."""
    exit_code = error.exit_code
    emit_json(
        {
            "error": {
                "code": "invalid_input",
                "message": str(error),
                "exit_code": exit_code,
            }
        }
    )
    raise SystemExit(exit_code) from error


def main() -> None:
    """Run the console-script entrypoint with JSON-aware usage errors."""
    if not _argv_requests_json(sys.argv[1:]):
        # Let Typer own human usage, rich error rendering, and exit handling.
        app()
        return
    try:
        result = app(standalone_mode=False)
    except typer.TyperException as error:
        _emit_typer_json_error(error)
    else:
        # Non-standalone Typer returns the code for explicit typer.Exit signals.
        if isinstance(result, int):
            raise SystemExit(result)
