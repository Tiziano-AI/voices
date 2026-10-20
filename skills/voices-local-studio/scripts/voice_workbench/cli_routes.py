"""Audit source routing for the voices prompt workbench."""

from __future__ import annotations

from pathlib import Path

from .audit import audit_json_spec_path, audit_jsonl_path, audit_txt_path
from .contracts import AuditItem, WorkbenchError


def audit_source_path(path: Path, default_text: str | None, strict_imitation: bool) -> tuple[list[AuditItem], str]:
    """Route one audit source path to the matching parser."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return audit_json_spec_path(path, default_text, strict_imitation), "json"
    if suffix == ".jsonl":
        return audit_jsonl_path(path, default_text, strict_imitation), "jsonl"
    if suffix == ".txt":
        return audit_txt_path(path, default_text, strict_imitation), "txt"
    raise WorkbenchError(f"Unsupported audit input '{suffix}'. Use .json, .jsonl, .txt, or --instruct.")
