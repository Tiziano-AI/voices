"""Structured voice-profile helpers."""

from __future__ import annotations

from .contracts import VoiceProfile


def populated_dimension_count_from_profile(profile: VoiceProfile) -> int:
    """Count the number of populated structured voice dimensions."""
    count = sum(
        1
        for value in (
            profile.gender,
            profile.age,
            profile.pitch,
            profile.pace,
            profile.emotion,
            profile.diction,
            profile.energy,
            profile.purpose,
            profile.archetype,
        )
        if value
    )
    return count + (1 if profile.characteristics else 0)
