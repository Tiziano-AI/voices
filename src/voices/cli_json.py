"""Shared CLI JSON envelopes and execution context."""

import json
from collections.abc import Callable
from dataclasses import dataclass

import typer
from pydantic import BaseModel, TypeAdapter, ValidationError

from voices.cli_support import exit_for_error
from voices.compute import LOCAL_COMPUTE, ComputeSelection
from voices.domain.errors import InvalidInputError, VoicesError

JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, object])
JSON_LIST_ADAPTER = TypeAdapter(list[object])


@dataclass(frozen=True, slots=True)
class CliContext:
    """Global CLI execution context derived from Typer callback options."""

    json_output: bool
    compute: ComputeSelection = LOCAL_COMPUTE


def context_from_typer(ctx: typer.Context) -> CliContext:
    """Return the current CLI execution context or the default human mode."""
    if isinstance(ctx.obj, CliContext):
        return ctx.obj
    return CliContext(json_output=False)


def model_object(model: BaseModel) -> dict[str, object]:
    """Return one Pydantic model as a JSON-compatible object."""
    return JSON_OBJECT_ADAPTER.validate_python(model.model_dump(mode="json"))


def emit_json(payload: dict[str, object] | list[object]) -> None:
    """Write one machine-readable JSON document to stdout."""
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def collection_payload(items: list[dict[str, object]], limit: int | None) -> dict[str, object]:
    """Build the canonical collection envelope for CLI JSON output."""
    return {
        "items": items,
        "count": len(items),
        "limit": limit,
    }


def error_payload(error: VoicesError) -> dict[str, object]:
    """Build the canonical machine-readable product error envelope."""
    return {
        "error": {
            "code": error.code,
            "message": str(error),
            "exit_code": error.exit_code,
        }
    }


def emit_error(error: VoicesError) -> None:
    """Write one JSON product error envelope to stdout."""
    emit_json(error_payload(error))


def run_cli_action(context: CliContext, action: Callable[[], None]) -> None:
    """Execute one command body with human or JSON domain-error rendering."""
    try:
        action()
    except VoicesError as error:
        if context.json_output:
            emit_error(error)
            raise SystemExit(error.exit_code) from error
        exit_for_error(error)


def require_json_readable_payload(value: object) -> dict[str, object] | list[object]:
    """Validate raw response JSON before emitting it through the CLI envelope."""
    try:
        if isinstance(value, list):
            return JSON_LIST_ADAPTER.validate_python(value)
        return JSON_OBJECT_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise InvalidInputError("Response did not contain a JSON object or array.") from exc


def require_limit(value: int | None) -> int | None:
    """Validate an optional collection limit."""
    if value is None:
        return None
    if value < 1:
        raise InvalidInputError("limit must be greater than zero.")
    return value
