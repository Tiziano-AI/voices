"""Prompt-fragment composition for voice specs."""

from __future__ import annotations

from .compose_use_parts import compose_archetype, compose_constraints, compose_diction, compose_purpose
from .compose_voice_parts import (
    compose_emotion_and_energy,
    compose_identity,
    compose_pace,
    compose_pitch,
    compose_timbre,
)
from .contracts import VoiceProfile


def compose_instruct(profile: VoiceProfile, prose_profile: str) -> str:
    """Compile one profile into deterministic prompt prose."""
    fragments = [
        compose_identity(profile),
        compose_pitch(profile, prose_profile),
        compose_pace(profile, prose_profile),
        compose_emotion_and_energy(profile, prose_profile),
        compose_timbre(profile, prose_profile),
        compose_diction(profile, prose_profile),
        compose_purpose(profile, prose_profile),
        compose_archetype(profile, prose_profile),
        compose_constraints(profile, prose_profile),
    ]
    return " ".join(fragment for fragment in fragments if fragment)
