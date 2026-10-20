"""Structured spec parsing for the voices workbench."""

from __future__ import annotations

import json
from pathlib import Path

from .compose_profile import populated_dimension_count_from_profile
from .compose_values import optional_string, require_object, require_string
from .compose_voice_payload import voice_profile
from .contracts import SUPPORTED_LANGUAGES, VOICE_ID_PATTERN, VoiceSpec, WorkbenchError


def starter_spec(index: int) -> dict[str, object]:
    """Return one starter structured spec."""
    return {
        "id": f"voice_{index:02d}",
        "name": "",
        "language": "English",
        "text": "",
        "voice": {
            "gender": "",
            "age": "",
            "pitch": "",
            "pace": "",
            "emotion": "",
            "characteristics": [],
            "diction": "",
            "energy": "",
            "purpose": "",
            "archetype": "",
            "constraints": [],
        },
    }


def load_json_path(path: Path) -> object:
    """Load one JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkbenchError(f"Input file '{path}' does not exist.") from exc
    except OSError as exc:
        raise WorkbenchError(f"Unable to read '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorkbenchError(f"Malformed JSON in '{path}': {exc}") from exc


def default_name_from_id(voice_id: str) -> str:
    """Derive a display name from a slug."""
    return voice_id.replace("_", " ").replace("-", " ").title()


def parse_spec_input(payload: object) -> list[VoiceSpec]:
    """Parse one structured spec object, or an array of them."""
    if isinstance(payload, list):
        return [parse_voice_spec(item, index + 1) for index, item in enumerate(payload)]
    return [parse_voice_spec(payload, 1)]


def parse_voice_spec(payload: object, position: int) -> VoiceSpec:
    """Parse one structured spec."""
    spec_object = require_object(payload, f"spec[{position}]")
    voice = voice_profile(require_object(spec_object.get("voice"), f"spec[{position}].voice"))
    if populated_dimension_count_from_profile(voice) == 0:
        raise WorkbenchError(f"spec[{position}] has no populated voice dimensions.")
    spec_id = require_string(spec_object.get("id"), f"spec[{position}].id")
    if not VOICE_ID_PATTERN.fullmatch(spec_id):
        raise WorkbenchError(f"spec[{position}].id '{spec_id}' does not satisfy the local voice_id grammar.")
    language = require_string(spec_object.get("language"), f"spec[{position}].language")
    if language not in SUPPORTED_LANGUAGES:
        raise WorkbenchError(f"spec[{position}].language '{language}' is not in the supported product set.")
    return VoiceSpec(
        id=spec_id,
        name=optional_string(spec_object.get("name")) or default_name_from_id(spec_id),
        language=language,
        text=optional_string(spec_object.get("text")),
        voice=voice,
    )
