"""Named-person and imitation-risk text rules."""

from __future__ import annotations

from .contracts import IMITATION_PATTERNS, NAME_PATTERN, STYLE_NAME_PATTERN, Diagnostic


def normalize_text(text: str) -> str:
    """Normalize prompt prose for imitation inspection."""
    return " ".join(text.lower().split())


def imitation_diagnostic(text: str, strict_imitation: bool) -> Diagnostic | None:
    """Detect direct named-person or explicit imitation language."""
    normalized = normalize_text(text)
    risky_pattern = any(pattern in normalized for pattern in IMITATION_PATTERNS)
    risky_name = bool(NAME_PATTERN.search(text))
    risky_style = bool(STYLE_NAME_PATTERN.search(text))
    if not any((risky_pattern, risky_name, risky_style)):
        return None
    return Diagnostic(
        level="error" if strict_imitation else "warn",
        code="imitation_risk",
        message="Prompt leans on named-person or imitation-style language; use original traits instead.",
    )
