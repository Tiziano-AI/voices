"""Typed HTTP contracts for the local bundled voices studio."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from voices import config
from voices.domain.contracts import (
    DEFAULT_LANGUAGE_LABEL,
    SUPPORTED_LANGUAGE_LABELS,
    OutputRecord,
    VoiceRecord,
    require_optional_supported_language,
    require_supported_language,
    require_voice_id,
    validate_output_artifact_name,
)
from voices.domain.create_contracts import GUIDED_RECORDING_SCRIPTS, TranscriptionSegment
from voices.domain.speech_contracts import SpeechInput, SpeechModelIdentity, SpeechReferenceIdentity
from voices.edge.errors import EdgeErrorPayload


def _require_non_empty(label: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


class UiConfigResponse(BaseModel):
    """Stable browser bootstrap payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supported_languages: tuple[str, ...] = SUPPORTED_LANGUAGE_LABELS
    default_language: str = DEFAULT_LANGUAGE_LABEL
    base_model_id: str = config.BASE_MODEL
    base_model_revision: str = config.BASE_MODEL_REVISION
    compute_backend: Literal["mlx", "dgx"] = "mlx"
    guided_record_target_seconds: float = config.GUIDED_RECORD_TARGET_SECONDS
    free_record_minimum_seconds: float = config.FREE_RECORD_MINIMUM_SECONDS
    guided_scripts: dict[str, str] = GUIDED_RECORDING_SCRIPTS


class VoiceSummary(BaseModel):
    """Compact voice projection for the playable rack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    language: str
    source_kind: str
    description: str
    created_at: str
    reference_sha256: str
    reference_text_sha256: str


class VoiceDetail(BaseModel):
    """Full voice detail projection for the inspector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: VoiceSummary
    record: VoiceRecord
    reference_text: str
    reference_audio_url: str


class PreviewRequest(BaseModel):
    """One immediate synthesized preview request."""

    model_config = ConfigDict(extra="forbid")

    voice_id: str
    text: str
    language: str | None = None
    expected_reference: SpeechReferenceIdentity | None = None
    expected_model: SpeechModelIdentity | None = None

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, value: str) -> str:
        """Require a saved-voice id before preview synthesis starts."""
        return require_voice_id(value)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Require non-empty preview text."""
        return _require_non_empty("text", value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        """Normalize optional preview language overrides."""
        return require_optional_supported_language(value)


class CompareRequest(BaseModel):
    """Compare one line across multiple saved voices."""

    model_config = ConfigDict(extra="forbid")

    voice_ids: list[str]
    text: str
    language: str | None = None
    expected_references: dict[str, SpeechReferenceIdentity] | None = None
    expected_model: SpeechModelIdentity | None = None
    expected_languages: dict[str, str] | None = None

    @field_validator("expected_languages")
    @classmethod
    def validate_expected_languages(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        """Validate observed per-voice languages before comparing saved defaults."""
        if value is None:
            return None
        return {
            require_voice_id(voice_id): require_supported_language(language) for voice_id, language in value.items()
        }

    @field_validator("voice_ids")
    @classmethod
    def validate_voice_ids(cls, value: list[str]) -> list[str]:
        """Require at least one saved-voice id for compare."""
        if not value:
            raise ValueError("voice_ids must not be empty")
        return [require_voice_id(voice_id) for voice_id in value]

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Require non-empty compare text."""
        return _require_non_empty("text", value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        """Normalize optional compare language overrides."""
        return require_optional_supported_language(value)


class PreviewClip(BaseModel):
    """One ephemeral playable clip exposed to the browser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str
    voice_id: str
    kind: str
    language: str
    audio_url: str
    input: SpeechInput


class CompareSuccess(BaseModel):
    """One playable comparison occurrence, independent of other voices' failures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    voice_id: str
    clip: PreviewClip
    error: None = None


class CompareFailure(BaseModel):
    """One failed comparison target without discarding successful occurrences."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    voice_id: str
    clip: None = None
    error: EdgeErrorPayload


CompareResult = CompareSuccess | CompareFailure


class RenderRequest(PreviewRequest):
    """Persist one rendered output."""


class RenderArtifact(BaseModel):
    """Browser projection for one persisted render artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: OutputRecord
    audio_url: str
    sidecar_url: str


class DesignRequest(BaseModel):
    """Create one designed voice from the browser studio."""

    model_config = ConfigDict(extra="forbid")

    name: str
    voice_id: str | None = None
    instruct: str
    text: str
    language: str = DEFAULT_LANGUAGE_LABEL
    overwrite: bool = False
    operation_token: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a display name for browser design saves."""
        return _require_non_empty("name", value)

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, value: str | None) -> str | None:
        """Normalize the optional browser-supplied design id."""
        if value is None:
            return None
        return require_voice_id(value)

    @field_validator("instruct", "text")
    @classmethod
    def validate_non_empty(cls, value: str, info: ValidationInfo) -> str:
        """Require design prompt and reference text."""
        return _require_non_empty(info.field_name or "value", value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize the required design language."""
        return require_supported_language(value)

    @field_validator("operation_token")
    @classmethod
    def validate_operation_token(cls, value: str | None) -> str | None:
        """Normalize the optional browser cancellation token."""
        if value is None:
            return None
        return _require_non_empty("operation_token", value)


class CloneReviewDraft(BaseModel):
    """Ephemeral review draft returned before clone save."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_token: str
    suggested_voice_id: str
    transcript: str
    language: str
    duration_seconds: float
    segments: list[TranscriptionSegment]
    audio_url: str


class CloneSaveRequest(BaseModel):
    """Persist one reviewed clone voice."""

    model_config = ConfigDict(extra="forbid")

    review_token: str
    voice_id: str
    name: str
    transcript: str
    overwrite: bool = False

    @field_validator("review_token")
    @classmethod
    def validate_review_token(cls, value: str) -> str:
        """Require the single-spend review token."""
        return _require_non_empty("review token", value)

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, value: str) -> str:
        """Require the destination saved-voice id."""
        return require_voice_id(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require the destination display name."""
        return _require_non_empty("name", value)

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str) -> str:
        """Require the operator-approved transcript."""
        return _require_non_empty("transcript", value)


class BatchDesignRow(BaseModel):
    """One row in the batch-design browser result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    voice_id: str
    name: str
    status: str
    detail: str


class BatchDesignResult(BaseModel):
    """Projected result for one browser batch-design action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dry_run: bool
    rows: list[BatchDesignRow]


class BatchDesignForm(BaseModel):
    """Validated multipart metadata for batch design upload."""

    model_config = ConfigDict(extra="forbid")

    language: str = DEFAULT_LANGUAGE_LABEL
    text: str | None = None
    overwrite: bool = False
    dry_run: bool = False
    operation_token: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize the batch default language."""
        return require_supported_language(value)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        """Normalize optional shared batch seed text."""
        if value is None:
            return None
        return _require_non_empty("text", value)

    @field_validator("operation_token")
    @classmethod
    def validate_operation_token(cls, value: str | None) -> str | None:
        """Normalize the optional batch cancellation token."""
        if value is None:
            return None
        return _require_non_empty("operation_token", value)


class CloneReviewForm(BaseModel):
    """Validated multipart metadata for clone review uploads."""

    model_config = ConfigDict(extra="forbid")

    language: str = DEFAULT_LANGUAGE_LABEL
    review_policy: Literal["import", "record_guided", "record_free"] = "import"
    transcript: str | None = None
    name: str | None = None
    voice_id: str | None = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Normalize the clone-review language."""
        return require_supported_language(value)

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str | None) -> str | None:
        """Normalize optional imported transcript text."""
        if value is None:
            return None
        return _require_non_empty("transcript", value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """Normalize the optional suggested clone name."""
        if value is None:
            return None
        return _require_non_empty("name", value)

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, value: str | None) -> str | None:
        """Normalize the optional suggested clone id."""
        if value is None:
            return None
        return require_voice_id(value)


class OutputDownloadTarget(BaseModel):
    """Safe output file projection for file download routes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    voice_id: str
    filename: str

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, value: str) -> str:
        """Require a valid output directory voice id."""
        return require_voice_id(value)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        """Require a canonical render artifact basename."""
        return validate_output_artifact_name(value)
