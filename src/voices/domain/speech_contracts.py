"""Effective synthesis inputs and optional caller preconditions."""

from pydantic import BaseModel, ConfigDict, Field


class SpeechReferenceIdentity(BaseModel):
    """Identify the exact WAV and transcript a caller selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SpeechModelIdentity(BaseModel):
    """Identify one immutable Base model selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_model_id: str = Field(min_length=1)
    base_model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")


class SpeechInput(SpeechReferenceIdentity, SpeechModelIdentity):
    """The actual input attached to one generated performance."""

    voice_id: str
    text: str
    language: str
