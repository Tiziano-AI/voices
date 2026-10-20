"""Audit command handler for the voices workbench."""

from __future__ import annotations

import argparse
import json

from .audit import audit_prose_item, json_ready_items, summarize_items
from .cli_report import print_text_report
from .cli_routes import audit_source_path
from .contracts import AuditItem, WorkbenchError


def handle_audit(args: argparse.Namespace) -> int:
    """Audit prompts, packs, or structured specs."""
    _validate_audit_inputs(args)
    if args.instruct is not None:
        items = [audit_prose_item("inline", args.instruct, args.strict_imitation)]
        input_kind = "inline"
    else:
        items, input_kind = audit_source_path(args.source, args.default_text, args.strict_imitation)
    summary = summarize_items(items)
    if args.json:
        payload = _json_payload(input_kind, args.strict_imitation, summary, items)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_text_report(input_kind, summary, items)
    return 1 if summary["errors"] > 0 else 0


def _validate_audit_inputs(args: argparse.Namespace) -> None:
    if args.instruct is None and args.source is None:
        raise WorkbenchError("Provide either --instruct or a source path.")
    if args.instruct is not None and args.source is not None:
        raise WorkbenchError("Use either --instruct or a source path, not both.")


def _json_payload(
    input_kind: str,
    strict_imitation: bool,
    summary: dict[str, int],
    items: list[AuditItem],
) -> dict[str, object]:
    return {
        "input_kind": input_kind,
        "strict_imitation": strict_imitation,
        "summary": summary,
        "items": json_ready_items(items),
    }
