"""Structured voice payload parsing."""

from __future__ import annotations

from .compose_values import optional_string, optional_string_list
from .contracts import VoiceProfile


def voice_profile(voice_payload: dict[str, object]) -> VoiceProfile:
    """Parse one structured voice payload."""
    return VoiceProfile(
        gender=optional_string(voice_payload.get("gender")),
        age=optional_string(voice_payload.get("age")),
        pitch=optional_string(voice_payload.get("pitch")),
        pace=optional_string(voice_payload.get("pace")),
        emotion=optional_string(voice_payload.get("emotion")),
        characteristics=tuple(optional_string_list(voice_payload.get("characteristics"), "characteristics")),
        diction=optional_string(voice_payload.get("diction")),
        energy=optional_string(voice_payload.get("energy")),
        purpose=optional_string(voice_payload.get("purpose")),
        archetype=optional_string(voice_payload.get("archetype")),
        constraints=tuple(optional_string_list(voice_payload.get("constraints"), "constraints")),
    )
