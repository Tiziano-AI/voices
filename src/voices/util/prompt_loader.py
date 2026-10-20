"""Load and validate batch voice-design prompt files."""

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from voices.domain.contracts import DesignPromptInput
from voices.domain.errors import InvalidPromptFileError
from voices.util.slug import voice_id_from_prompt

JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, object])


def load_prompts(
    path: Path,
    default_text: str | None,
    default_language: str,
) -> list[DesignPromptInput]:
    """Load a JSONL or TXT prompt file into validated design prompts."""
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return _load_jsonl(path, default_text, default_language)
    if suffix == ".txt":
        return _load_txt(path, default_text, default_language)
    raise InvalidPromptFileError(f"Unsupported prompt file format '{suffix}'. Use .jsonl or .txt.")


def _load_jsonl(
    path: Path,
    default_text: str | None,
    default_language: str,
) -> list[DesignPromptInput]:
    """Load newline-delimited prompt objects from a JSONL file."""
    prompts: list[DesignPromptInput] = []
    try:
        with path.open(encoding="utf-8") as prompt_file:
            for line_number, line in enumerate(prompt_file, start=1):
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                try:
                    payload_object: object = json.loads(stripped_line)
                except json.JSONDecodeError as exc:
                    raise InvalidPromptFileError(f"Malformed JSON on line {line_number}: {exc}") from exc
                try:
                    payload = JSON_OBJECT_ADAPTER.validate_python(payload_object)
                except ValidationError as exc:
                    raise InvalidPromptFileError(f"Line {line_number}: each JSONL row must be an object.") from exc
                if "name" not in payload:
                    payload["name"] = str(payload.get("id", "")).replace("_", " ").replace("-", " ").title()
                if "text" not in payload:
                    payload["text"] = default_text
                if "language" not in payload:
                    payload["language"] = default_language
                try:
                    prompts.append(DesignPromptInput.model_validate(payload))
                except ValidationError as exc:
                    raise InvalidPromptFileError(f"Line {line_number}: invalid prompt entry: {exc}") from exc
    except OSError as exc:
        raise InvalidPromptFileError(f"Unable to read prompt file '{path}': {exc}") from exc
    return prompts


def _load_txt(
    path: Path,
    default_text: str | None,
    default_language: str,
) -> list[DesignPromptInput]:
    """Load one voice-design prompt per non-comment line from a TXT file."""
    if not default_text:
        raise InvalidPromptFileError("A .txt prompt file requires --text to provide global seed text.")
    prompts: list[DesignPromptInput] = []
    try:
        with path.open(encoding="utf-8") as prompt_file:
            for line_number, line in enumerate(prompt_file, start=1):
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith("#"):
                    continue
                voice_id = voice_id_from_prompt(stripped_line)
                try:
                    prompts.append(
                        DesignPromptInput.model_validate(
                            {
                                "id": voice_id,
                                "instruct": stripped_line,
                                "name": voice_id.replace("-", " ").title(),
                                "text": default_text,
                                "language": default_language,
                            }
                        )
                    )
                except ValidationError as exc:
                    raise InvalidPromptFileError(f"Line {line_number}: invalid prompt entry: {exc}") from exc
    except OSError as exc:
        raise InvalidPromptFileError(f"Unable to read prompt file '{path}': {exc}") from exc
    return prompts
