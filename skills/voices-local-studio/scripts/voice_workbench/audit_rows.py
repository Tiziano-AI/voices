"""Structured and JSONL row audit helpers."""

from __future__ import annotations

from .audit_profile import (
    append_id_diagnostics,
    append_language_diagnostics,
    profile_from_voice,
    profile_imitation_probe,
)
from .audit_text import audit_prose_item, imitation_diagnostic
from .audit_values import missing_seed_text
from .compose_profile import populated_dimension_count_from_profile
from .contracts import AuditItem, Diagnostic


def audit_structured_object(
    label: str,
    payload: dict[str, object],
    default_text: str | None,
    strict_imitation: bool,
) -> AuditItem:
    """Audit one structured spec object."""
    diagnostics: list[Diagnostic] = []
    append_id_diagnostics(diagnostics, "Structured spec", payload.get("id"))
    append_language_diagnostics(diagnostics, payload.get("language"))
    voice_value = payload.get("voice")
    if not isinstance(voice_value, dict):
        diagnostics.append(Diagnostic("error", "pack_row_missing_required_fields", "Voice object is missing."))
        return AuditItem(label=label, diagnostics=tuple(diagnostics))
    profile = profile_from_voice(voice_value)
    if populated_dimension_count_from_profile(profile) < 3:
        diagnostics.append(Diagnostic("warn", "missing_dimensions", "Structured spec covers fewer dimensions."))
    if not profile.purpose:
        diagnostics.append(Diagnostic("note", "missing_use_case", "Structured spec does not state a purpose."))
    if missing_seed_text(payload.get("text"), default_text):
        diagnostics.append(Diagnostic("error", "missing_seed_text", "Structured spec needs non-empty text."))
    imitation = imitation_diagnostic(profile_imitation_probe(profile), strict_imitation)
    if imitation is not None:
        diagnostics.append(imitation)
    return AuditItem(label=label, diagnostics=tuple(diagnostics))


def audit_jsonl_row(
    label: str,
    payload: dict[str, object],
    default_text: str | None,
    strict_imitation: bool,
) -> AuditItem:
    """Audit one JSONL prompt row."""
    diagnostics: list[Diagnostic] = []
    append_id_diagnostics(diagnostics, "Row", payload.get("id"))
    instruct = payload.get("instruct")
    if not isinstance(instruct, str) or not instruct.strip():
        diagnostics.append(Diagnostic("error", "pack_row_missing_required_fields", "Row is missing instruct."))
        return AuditItem(label=label, diagnostics=tuple(diagnostics))
    language = payload.get("language")
    if language is not None:
        append_language_diagnostics(diagnostics, language)
    if missing_seed_text(payload.get("text"), default_text):
        diagnostics.append(Diagnostic("error", "missing_seed_text", "Row needs non-empty text."))
    diagnostics.extend(audit_prose_item(label, instruct, strict_imitation).diagnostics)
    return AuditItem(label=label, diagnostics=tuple(diagnostics))
