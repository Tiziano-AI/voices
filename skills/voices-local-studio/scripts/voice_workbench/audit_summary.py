"""Audit summary helpers."""

from __future__ import annotations

from dataclasses import asdict

from .contracts import AuditItem


def summarize_items(items: list[AuditItem]) -> dict[str, int]:
    """Count findings by level."""
    summary = {"errors": 0, "warnings": 0, "notes": 0}
    keys = {"error": "errors", "warn": "warnings", "note": "notes"}
    for item in items:
        for diagnostic in item.diagnostics:
            key = keys.get(diagnostic.level)
            if key is not None:
                summary[key] += 1
    return summary


def json_ready_items(items: list[AuditItem]) -> list[dict[str, object]]:
    """Convert audit items to JSON-ready dictionaries."""
    return [asdict(item) for item in items]
