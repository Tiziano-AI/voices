"""Structured-spec value validation helpers."""

from __future__ import annotations

from .contracts import WorkbenchError


def require_object(value: object, label: str) -> dict[str, object]:
    """Require a JSON object."""
    if not isinstance(value, dict):
        raise WorkbenchError(f"{label} must be an object.")
    return value


def require_string(value: object, label: str) -> str:
    """Require a non-empty string."""
    if not isinstance(value, str):
        raise WorkbenchError(f"{label} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise WorkbenchError(f"{label} must not be empty.")
    return stripped


def optional_string(value: object) -> str:
    """Return a stripped string after validating its type."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise WorkbenchError("Expected a string field.")
    return value.strip()


def optional_string_list(value: object, label: str) -> list[str]:
    """Return a validated list of stripped strings."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise WorkbenchError(f"{label} must be a list of strings.")
    return _string_items(value, label)


def _string_items(value: list[object], label: str) -> list[str]:
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise WorkbenchError(f"{label} must contain only strings.")
        stripped = item.strip()
        if stripped:
            items.append(stripped)
    return items
