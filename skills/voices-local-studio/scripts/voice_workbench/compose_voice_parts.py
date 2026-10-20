"""Voice-quality prompt fragments."""

from __future__ import annotations

from .compose_text import capitalize_fragment, join_with_commas
from .contracts import VoiceProfile


def compose_identity(profile: VoiceProfile) -> str:
    """Compose the identity fragment."""
    bits = [bit for bit in (profile.age, profile.gender) if bit]
    return "" if not bits else f"{capitalize_fragment(' '.join(bits))} voice."


def compose_pitch(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the pitch fragment."""
    if not profile.pitch:
        return ""
    label = "pitch" if prose_profile == "plain" else "register"
    return f"{capitalize_fragment(profile.pitch)} {label}."


def compose_pace(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the pace fragment."""
    if not profile.pace:
        return ""
    label = "pace" if prose_profile == "plain" else "pacing"
    return f"{capitalize_fragment(profile.pace)} {label}."


def compose_emotion_and_energy(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the emotion and energy fragment."""
    bits = [bit for bit in (profile.emotion, profile.energy) if bit]
    if not bits:
        return ""
    if len(bits) == 1:
        label = "energy" if prose_profile == "plain" else "emotional tone"
        return f"{capitalize_fragment(bits[0])} {label}."
    return f"{capitalize_fragment(bits[0])} emotion with {bits[1]} energy."


def compose_timbre(profile: VoiceProfile, prose_profile: str) -> str:
    """Compose the timbre fragment."""
    if not profile.characteristics:
        return ""
    label = "characteristics" if prose_profile == "plain" else "timbre"
    return f"{capitalize_fragment(join_with_commas(profile.characteristics))} {label}."
