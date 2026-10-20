"""File-path audit routers."""

from __future__ import annotations

import json
from pathlib import Path

from .audit_rows import audit_jsonl_row, audit_structured_object
from .audit_text import audit_prose_item
from .compose_parse import load_json_path
from .contracts import AuditItem, Diagnostic, WorkbenchError


def audit_json_spec_path(path: Path, default_text: str | None, strict_imitation: bool) -> list[AuditItem]:
    """Audit a JSON structured spec, or an array of specs."""
    payload = load_json_path(path)
    objects = payload if isinstance(payload, list) else [payload]
    items: list[AuditItem] = []
    for index, item in enumerate(objects, start=1):
        if isinstance(item, dict):
            items.append(audit_structured_object(f"spec[{index}]", item, default_text, strict_imitation))
        else:
            items.append(_invalid_item(f"spec[{index}]", "Structured spec entry must be an object."))
    return items


def _invalid_item(label: str, message: str) -> AuditItem:
    return AuditItem(label=label, diagnostics=(Diagnostic("error", "pack_row_missing_required_fields", message),))


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise WorkbenchError(f"Input file '{path}' does not exist.") from exc
    except OSError as exc:
        raise WorkbenchError(f"Unable to read '{path}': {exc}") from exc


def audit_jsonl_path(path: Path, default_text: str | None, strict_imitation: bool) -> list[AuditItem]:
    """Audit a JSONL prompt pack."""
    items: list[AuditItem] = []
    for line_number, line in enumerate(_read_lines(path), start=1):
        stripped = line.strip()
        if stripped:
            items.append(_audit_jsonl_line(line_number, stripped, default_text, strict_imitation))
    return items


def _audit_jsonl_line(
    line_number: int,
    stripped: str,
    default_text: str | None,
    strict_imitation: bool,
) -> AuditItem:
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return _invalid_item(f"line {line_number}", f"Malformed JSON: {exc}")
    if not isinstance(payload, dict):
        return _invalid_item(f"line {line_number}", "Each JSONL row must be an object.")
    return audit_jsonl_row(f"line {line_number}", payload, default_text, strict_imitation)


def audit_txt_path(path: Path, default_text: str | None, strict_imitation: bool) -> list[AuditItem]:
    """Audit a TXT prompt pack."""
    items = _txt_seed_items(path, default_text)
    for line_number, line in enumerate(_read_lines(path), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            items.append(audit_prose_item(f"line {line_number}", stripped, strict_imitation))
    return items


def _txt_seed_items(path: Path, default_text: str | None) -> list[AuditItem]:
    if default_text is not None and default_text.strip():
        return []
    return [
        AuditItem(
            str(path),
            (Diagnostic("error", "missing_text_for_txt_pack", "TXT prompt packs require shared seed text."),),
        )
    ]
