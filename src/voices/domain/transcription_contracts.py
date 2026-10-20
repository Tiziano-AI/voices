"""Audio-only transcription results without a voice-library or timing claim."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from voices.domain.audio_contracts import AudioIdentity
from voices.domain.contracts import _validate_non_empty
from voices.runtime_identity import RuntimeIdentity


class TranscriptionResult(BaseModel):
    """One recognized transcript bound to its input bytes and inference identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transcript: str
    language: str
    model_id: str
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime: RuntimeIdentity
    audio: AudioIdentity

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str) -> str:
        return _validate_non_empty("transcript", value)
