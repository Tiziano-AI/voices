"""Small value-normalization helpers for prompt audits."""

from __future__ import annotations


def optional_string_for_audit(value: object) -> str:
    """Return a stripped string for audit paths without raising."""
    return value.strip() if isinstance(value, str) else ""


def optional_string_list_for_audit(value: object) -> list[str]:
    """Return stripped strings for audit paths without raising."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def has_seed_text(value: object) -> bool:
    """Return whether one prompt path has usable non-empty seed text."""
    return isinstance(value, str) and bool(value.strip())


def missing_seed_text(value: object, default_text: str | None) -> bool:
    """Return whether neither local nor shared seed text is usable."""
    return not any((has_seed_text(value), has_seed_text(default_text)))
