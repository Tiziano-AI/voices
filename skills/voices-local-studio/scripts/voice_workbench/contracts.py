"""Shared contracts for the voices prompt workbench."""

import re
from dataclasses import dataclass

SUPPORTED_LANGUAGES = (
    "Chinese",
    "English",
    "French",
    "German",
    "Italian",
    "Japanese",
    "Korean",
    "Portuguese",
    "Russian",
    "Spanish",
)
VOICE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
WORD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z'-]*")
DOUBLE_INTENSIFIER_PATTERN = re.compile(r"\b(very|really|extremely)\b(?:[\s,;:-]+\b\1\b)+", re.IGNORECASE)
SUBJECTIVE_PATTERNS = (
    "my favorite",
    "favourite",
    "i love",
    "best voice",
    "sounds good",
    "sounds nice",
    "cool voice",
    "beautiful voice",
)
VAGUE_PATTERNS = (
    "nice voice",
    "good voice",
    "normal voice",
    "pleasant voice",
    "cool voice",
    "beautiful voice",
)
VAGUE_TOKENS = ("nice", "good", "normal", "pleasant", "cool", "beautiful", "great", "awesome")
IMITATION_PATTERNS = (
    "sound like",
    "sounds like",
    "in the voice of",
    "imitate",
    "mimic",
    "celebrity",
    "actor",
    "actress",
)
STYLE_NAME_PATTERN = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}(?:-style|'s\s+(?:voice|tone|sound)|\s+(?:style|voice|tone|sound))\b"
)
DIMENSION_TERMS: dict[str, tuple[str, ...]] = {
    "identity": (
        "male",
        "female",
        "neutral",
        "man",
        "woman",
        "child",
        "teen",
        "teenager",
        "young",
        "middle-aged",
        "elderly",
        "old",
    ),
    "pitch": ("high", "low", "mid", "register", "baritone", "bass", "tenor", "contralto", "soprano"),
    "pace": (
        "fast",
        "slow",
        "rapid",
        "deliberate",
        "clipped",
        "unhurried",
        "measured",
        "rushed",
        "pace",
        "cadence",
    ),
    "emotion": (
        "warm",
        "cold",
        "calm",
        "playful",
        "restrained",
        "serious",
        "soothing",
        "gentle",
        "energetic",
        "confident",
        "authority",
        "authoritative",
    ),
    "timbre": (
        "smoky",
        "gravelly",
        "crisp",
        "breathy",
        "resonant",
        "nasal",
        "hoarse",
        "mellow",
        "rich",
        "powerful",
        "dry",
        "bright",
        "dark",
    ),
}
PURPOSE_TERMS = (
    "narration",
    "narrator",
    "audiobook",
    "broadcast",
    "radio",
    "documentary",
    "explainer",
    "assistant",
    "ivr",
    "reviewer",
    "host",
    "podcast",
    "advert",
    "ad",
    "commercial",
    "character",
    "story",
    "storytelling",
    "asmr",
)
NAME_PATTERN = re.compile(r"\b(?:like|Like|think|Think)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")


class WorkbenchError(Exception):
    """Raised when the workbench input or command is invalid."""


@dataclass(frozen=True)
class Diagnostic:
    """One audit finding."""

    level: str
    code: str
    message: str


@dataclass(frozen=True)
class VoiceProfile:
    """Structured voice dimensions."""

    gender: str = ""
    age: str = ""
    pitch: str = ""
    pace: str = ""
    emotion: str = ""
    characteristics: tuple[str, ...] = ()
    diction: str = ""
    energy: str = ""
    purpose: str = ""
    archetype: str = ""
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class VoiceSpec:
    """Structured serious-authoring input."""

    id: str
    name: str
    language: str
    text: str
    voice: VoiceProfile


@dataclass(frozen=True)
class AuditItem:
    """Audit result for one prompt or structured entry."""

    label: str
    diagnostics: tuple[Diagnostic, ...] = ()
