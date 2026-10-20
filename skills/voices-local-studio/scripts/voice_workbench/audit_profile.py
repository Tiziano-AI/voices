"""Structured voice-profile audit helpers."""

from __future__ import annotations

from .audit_values import optional_string_for_audit, optional_string_list_for_audit
from .contracts import SUPPORTED_LANGUAGES, VOICE_ID_PATTERN, Diagnostic, VoiceProfile


def append_id_diagnostics(diagnostics: list[Diagnostic], label: str, value: object) -> None:
    """Append identifier diagnostics for one row label."""
    if not isinstance(value, str) or not value.strip():
        diagnostics.append(Diagnostic("error", "pack_row_missing_required_fields", f"{label} is missing id."))
    elif not VOICE_ID_PATTERN.fullmatch(value.strip()):
        diagnostics.append(Diagnostic("error", "invalid_voice_id", f"{label} id does not satisfy grammar."))


def append_language_diagnostics(diagnostics: list[Diagnostic], value: object) -> None:
    """Append language diagnostics for one structured value."""
    if not isinstance(value, str) or not value.strip():
        diagnostics.append(Diagnostic("error", "unsupported_language", "Language is missing."))
    elif value.strip() not in SUPPORTED_LANGUAGES:
        diagnostics.append(Diagnostic("error", "unsupported_language", f"Language '{value.strip()}' is unsupported."))


def profile_from_voice(voice_value: dict[str, object]) -> VoiceProfile:
    """Build a voice profile from an audit payload."""
    return VoiceProfile(
        gender=optional_string_for_audit(voice_value.get("gender")),
        age=optional_string_for_audit(voice_value.get("age")),
        pitch=optional_string_for_audit(voice_value.get("pitch")),
        pace=optional_string_for_audit(voice_value.get("pace")),
        emotion=optional_string_for_audit(voice_value.get("emotion")),
        characteristics=tuple(optional_string_list_for_audit(voice_value.get("characteristics"))),
        diction=optional_string_for_audit(voice_value.get("diction")),
        energy=optional_string_for_audit(voice_value.get("energy")),
        purpose=optional_string_for_audit(voice_value.get("purpose")),
        archetype=optional_string_for_audit(voice_value.get("archetype")),
        constraints=tuple(optional_string_list_for_audit(voice_value.get("constraints"))),
    )


def profile_imitation_probe(profile: VoiceProfile) -> str:
    """Return the full structured voice text used for imitation checks."""
    return " ".join(
        (
            profile.gender,
            profile.age,
            profile.pitch,
            profile.pace,
            profile.emotion,
            " ".join(profile.characteristics),
            profile.diction,
            profile.energy,
            profile.purpose,
            profile.archetype,
            " ".join(profile.constraints),
        )
    )
