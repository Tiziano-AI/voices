"""Validated persisted and API contracts for the voices product."""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from voices.domain.errors import InvalidInputError
from voices.runtime_identity import RuntimeIdentity

VOICE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
OUTPUT_ARTIFACT_NAME_PATTERN = re.compile(r"^\d{8}T\d{6}Z(?:__[a-z0-9]+(?:-[a-z0-9]+)*)?(?:-\d+)?\.(?:wav|json)$")
OUTPUT_AUDIO_SUFFIXES = frozenset((".wav",))
OUTPUT_ARTIFACT_SUFFIXES = frozenset((".wav", ".json"))
SUPPORTED_LANGUAGE_LABELS = (
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
DEFAULT_LANGUAGE_LABEL = "English"
_SUPPORTED_LANGUAGE_SET = frozenset(SUPPORTED_LANGUAGE_LABELS)


def _validate_timestamp(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return value


def _validate_voice_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("voice id must not be empty")
    if not VOICE_ID_PATTERN.fullmatch(normalized):
        raise ValueError("voice id must match ^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
    return normalized


def _validate_non_empty(label: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def _validate_output_artifact_name(label: str, value: str, suffixes: frozenset[str]) -> str:
    normalized = _validate_non_empty(label, value)
    artifact_path = Path(normalized)
    if artifact_path.name != normalized:
        raise ValueError(f"{label} must be a basename")
    if artifact_path.suffix not in suffixes:
        raise ValueError(f"{label} must use one of: {', '.join(sorted(suffixes))}")
    if OUTPUT_ARTIFACT_NAME_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{label} must be a canonical render artifact name")
    return normalized


def _validate_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ValueError("reference sha256 must be a 64-character hex digest")
    int(normalized, 16)
    return normalized


def _validate_supported_language(value: str) -> str:
    normalized = _validate_non_empty("language", value).title()
    if normalized not in _SUPPORTED_LANGUAGE_SET:
        supported = ", ".join(SUPPORTED_LANGUAGE_LABELS)
        raise ValueError(f"language must be one of: {supported}")
    return normalized


def require_voice_id(value: str) -> str:
    """Validate one public `voice_id` input and raise a product input error on failure."""
    try:
        return _validate_voice_id(value)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc


def require_supported_language(value: str) -> str:
    """Validate one required product language label and raise a product input error on failure."""
    try:
        return _validate_supported_language(value)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc


def require_non_empty_text(label: str, value: str) -> str:
    """Validate one required non-empty text field and raise a product input error on failure."""
    try:
        return _validate_non_empty(label, value)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc


def validate_output_artifact_name(value: str) -> str:
    """Validate one canonical render artifact basename for Pydantic contract owners."""
    return _validate_output_artifact_name("output artifact name", value, OUTPUT_ARTIFACT_SUFFIXES)


def require_optional_supported_language(value: str | None) -> str | None:
    """Validate one optional product language label and preserve `None`."""
    if value is None:
        return None
    return require_supported_language(value)


class DesignVoiceSource(BaseModel):
    """Voice provenance for references generated through VoiceDesign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["design"]
    model_id: str
    instruct: str

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        """Reject blank design model identifiers."""
        return _validate_non_empty("design model id", value)

    @field_validator("instruct")
    @classmethod
    def validate_instruct(cls, value: str) -> str:
        """Reject blank voice design prompts."""
        return _validate_non_empty("voice design prompt", value)


class ClonedVoiceSource(BaseModel):
    """Voice provenance for imported reference audio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["clone"]


VoiceSource = Annotated[
    DesignVoiceSource | ClonedVoiceSource,
    Field(discriminator="kind"),
]


class VoiceRecord(BaseModel):
    """Persisted metadata for one saved reference voice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    id: str
    name: str
    created_at: str
    language: str
    base_model_id: str
    reference_text: str
    reference_sha256: str
    source: VoiceSource

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Reject blank or path-like voice ids."""
        return _validate_voice_id(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Reject blank voice display names."""
        return _validate_non_empty("voice name", value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Require canonical UTC timestamps."""
        return _validate_timestamp(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize display languages to title case."""
        return _validate_supported_language(value)

    @field_validator("base_model_id")
    @classmethod
    def validate_base_model_id(cls, value: str) -> str:
        """Reject blank base model identifiers."""
        return _validate_non_empty("base model id", value)

    @field_validator("reference_text")
    @classmethod
    def validate_reference_text(cls, value: str) -> str:
        """Reject blank reference transcripts."""
        return _validate_non_empty("reference text", value)

    @field_validator("reference_sha256")
    @classmethod
    def validate_reference_sha256(cls, value: str) -> str:
        """Require SHA-256 digests once a voice is persisted."""
        return _validate_sha256(value)

    def source_kind(self) -> str:
        """Return the stable provenance discriminator for UI and CLI summaries."""
        return self.source.kind

    @property
    def reference_text_sha256(self) -> str:
        """Identify the exact normalized transcript consumed by synthesis."""
        return hashlib.sha256(self.reference_text.encode("utf-8")).hexdigest()

    def description(self) -> str:
        """Return the canonical human-readable source description."""
        if isinstance(self.source, DesignVoiceSource):
            return self.source.instruct
        return "Imported reference voice"


class VoiceDraft(BaseModel):
    """In-memory voice metadata before the reference SHA is known."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    created_at: str
    language: str
    base_model_id: str
    reference_text: str
    source: VoiceSource

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Reject blank or path-like voice ids."""
        return _validate_voice_id(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Reject blank voice display names."""
        return _validate_non_empty("voice name", value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Require canonical UTC timestamps."""
        return _validate_timestamp(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize display languages to title case."""
        return _validate_supported_language(value)

    @field_validator("base_model_id")
    @classmethod
    def validate_base_model_id(cls, value: str) -> str:
        """Reject blank base model identifiers."""
        return _validate_non_empty("base model id", value)

    @field_validator("reference_text")
    @classmethod
    def validate_reference_text(cls, value: str) -> str:
        """Reject blank reference transcripts."""
        return _validate_non_empty("reference text", value)


class OutputRecord(BaseModel):
    """Persisted metadata for one rendered output artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    voice_id: str
    created_at: str
    language: str
    base_model_id: str
    # Absent on historical schema-v2 sidecars; unknown must stay unknown.
    base_model_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None = None
    runtime: RuntimeIdentity | None = None
    text: str
    output_audio: str
    reference_voice_id: str
    reference_sha256: str
    reference_text_sha256: str | None = None

    @field_validator("voice_id", "reference_voice_id")
    @classmethod
    def validate_voice_ids(cls, value: str) -> str:
        """Reject blank or path-like voice ids."""
        return _validate_voice_id(value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Require canonical UTC timestamps."""
        return _validate_timestamp(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize display languages to title case."""
        return _validate_supported_language(value)

    @field_validator("base_model_id")
    @classmethod
    def validate_base_model_id(cls, value: str) -> str:
        """Reject blank base model identifiers."""
        return _validate_non_empty("base model id", value)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject blank synthesized text."""
        return _validate_non_empty("text", value)

    @field_validator("output_audio")
    @classmethod
    def validate_output_audio(cls, value: str) -> str:
        """Require the canonical WAV basename stored by the matching sidecar."""
        return _validate_output_artifact_name("output audio name", value, OUTPUT_AUDIO_SUFFIXES)

    @field_validator("reference_sha256")
    @classmethod
    def validate_reference_sha256(cls, value: str) -> str:
        """Require SHA-256 digests for render provenance."""
        return _validate_sha256(value)

    @field_validator("reference_text_sha256")
    @classmethod
    def validate_reference_text_sha256(cls, value: str | None) -> str | None:
        """Preserve unknown historical transcripts without backfilling them."""
        return None if value is None else _validate_sha256(value)


class OutputDraft(BaseModel):
    """In-memory render metadata before the output file name is known."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    voice_id: str
    created_at: str
    language: str
    base_model_id: str
    base_model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime: RuntimeIdentity
    text: str
    reference_voice_id: str
    reference_sha256: str
    reference_text_sha256: str

    @field_validator("voice_id", "reference_voice_id")
    @classmethod
    def validate_voice_ids(cls, value: str) -> str:
        """Reject blank or path-like voice ids."""
        return _validate_voice_id(value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Require canonical UTC timestamps."""
        return _validate_timestamp(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize display languages to title case."""
        return _validate_supported_language(value)

    @field_validator("base_model_id")
    @classmethod
    def validate_base_model_id(cls, value: str) -> str:
        """Reject blank base model identifiers."""
        return _validate_non_empty("base model id", value)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject blank synthesized text."""
        return _validate_non_empty("text", value)

    @field_validator("reference_sha256", "reference_text_sha256")
    @classmethod
    def validate_reference_sha256(cls, value: str) -> str:
        """Require SHA-256 digests for render provenance."""
        return _validate_sha256(value)


class DesignPromptInput(BaseModel):
    """Validated batch input for reference voice creation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    instruct: str
    name: str = ""
    text: str | None = None
    language: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        """Reject blank or path-like ids."""
        return _validate_voice_id(value)

    @field_validator("instruct")
    @classmethod
    def validate_instruct(cls, value: str) -> str:
        """Reject blank design prompts."""
        return _validate_non_empty("voice design prompt", value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Allow blank names for auto-generated display names."""
        return value.strip()

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        """Normalize optional seed text."""
        if value is None:
            return None
        return _validate_non_empty("seed text", value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        """Normalize optional language labels."""
        if value is None:
            return None
        return _validate_supported_language(value)
