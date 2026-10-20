"""Small text helpers for prompt composition."""

from __future__ import annotations


def capitalize_fragment(value: str) -> str:
    """Capitalize the first non-space character."""
    stripped = value.strip()
    if not stripped:
        return ""
    return stripped[0].upper() + stripped[1:]


def join_with_commas(values: tuple[str, ...] | list[str], conjunction: str = "and") -> str:
    """Join values with English commas."""
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} {conjunction} {values[1]}"
    head = ", ".join(values[:-1])
    return f"{head}, {conjunction} {values[-1]}"
