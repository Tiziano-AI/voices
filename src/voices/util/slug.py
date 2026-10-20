import hashlib
import re


def slugify(text: str, max_length: int = 40) -> str:
    """Normalize one human-authored label into a bounded lowercase slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if len(s) > max_length:
        s = s[:max_length].rstrip("-")
    return s


def voice_id_from_name(name: str) -> str:
    """Derive one public `voice_id` from a display name with a safe fallback."""
    slug = slugify(name, max_length=40)
    return slug if slug else "voice"


def display_name_from_voice_id(voice_id: str) -> str:
    """Project one saved `voice_id` back into a readable display label."""
    return voice_id.replace("_", " ").replace("-", " ").title()


def voice_id_from_prompt(instruct: str) -> str:
    """Derive one deterministic prompt-based voice id with a short hash suffix."""
    slug = slugify(instruct, max_length=30)
    h = hashlib.sha256(instruct.encode()).hexdigest()[:6]
    return f"{slug}-{h}" if slug else h
