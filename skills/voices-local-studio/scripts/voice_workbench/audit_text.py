"""Prose prompt audit entrypoint."""

from __future__ import annotations

from .audit_dimensions import contains_purpose, contains_vague_language, populated_dimension_count_from_text
from .audit_imitation import imitation_diagnostic
from .contracts import DOUBLE_INTENSIFIER_PATTERN, SUBJECTIVE_PATTERNS, AuditItem, Diagnostic


def audit_prose_item(label: str, instruct: str, strict_imitation: bool) -> AuditItem:
    """Audit one prose prompt."""
    diagnostics: list[Diagnostic] = []
    normalized = normalize_text(instruct)
    if populated_dimension_count_from_text(normalized) < 3:
        diagnostics.append(Diagnostic("warn", "missing_dimensions", "Prompt covers fewer than three dimensions."))
    if contains_vague_language(normalized):
        diagnostics.append(Diagnostic("warn", "too_vague", "Prompt uses vague praise without audible traits."))
    if any(pattern in normalized for pattern in SUBJECTIVE_PATTERNS):
        diagnostics.append(Diagnostic("warn", "too_subjective", "Prompt uses subjective preference language."))
    if DOUBLE_INTENSIFIER_PATTERN.search(instruct):
        diagnostics.append(Diagnostic("warn", "redundant_padding", "Prompt repeats intensifiers."))
    if not contains_purpose(normalized):
        diagnostics.append(Diagnostic("note", "missing_use_case", "Prompt does not clearly state a role."))
    imitation = imitation_diagnostic(instruct, strict_imitation)
    if imitation is not None:
        diagnostics.append(imitation)
    return AuditItem(label=label, diagnostics=tuple(diagnostics))


def normalize_text(text: str) -> str:
    """Normalize prompt prose for heuristic inspection."""
    return " ".join(text.lower().split())
