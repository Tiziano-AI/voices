"""Human-readable audit reporting."""

from __future__ import annotations

from .contracts import AuditItem


def print_text_report(input_kind: str, summary: dict[str, int], items: list[AuditItem]) -> None:
    """Print the human-readable audit report."""
    print(f"input_kind: {input_kind}")
    print(f"summary: {summary['errors']} error(s), {summary['warnings']} warning(s), {summary['notes']} note(s)")
    for item in items:
        print()
        print(f"[{item.label}]")
        if not item.diagnostics:
            print("- ok: no findings")
        for diagnostic in item.diagnostics:
            print(f"- {diagnostic.level} {diagnostic.code}: {diagnostic.message}")
