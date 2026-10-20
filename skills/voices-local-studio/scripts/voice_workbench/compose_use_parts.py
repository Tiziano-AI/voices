"""Use-case prompt fragments."""

from __future__ import annotations

from .compose_text import capitalize_fragment, join_with_commas
from .contracts import VoiceProfile


def compose_diction(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the diction fragment."""
    if not profile.diction:
        return ""
    if prose_profile == "plain":
        return f"Diction: {profile.diction}."
    return f"{capitalize_fragment(profile.diction)} diction."


def compose_purpose(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the purpose fragment."""
    if not profile.purpose:
        return ""
    if prose_profile == "plain":
        return f"Purpose: {profile.purpose}."
    return f"Built for {profile.purpose}."


def compose_archetype(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the archetype fragment."""
    if not profile.archetype:
        return ""
    if prose_profile == "plain":
        return f"Archetype: {profile.archetype}."
    if prose_profile == "balanced":
        return f"The archetype is {profile.archetype}."
    return f"Carries the bearing of a {profile.archetype}."


def compose_constraints(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the negative-constraints fragment."""
    if not profile.constraints:
        return ""
    joined = join_with_commas(profile.constraints, conjunction="and")
    if prose_profile == "plain":
        return f"Constraints: {joined}."
    return f"Keep it {joined}."
