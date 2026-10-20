"""Supplied-text alignment results, without transcription or correction claims."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from voices.domain.audio_contracts import AudioIdentity
from voices.runtime_identity import RuntimeIdentity


class AlignmentWord(BaseModel):
    """One upstream token; zero-width estimates remain zero-width."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)

    text: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_span(self) -> Self:
        if not self.text.strip() or self.end < self.start:
            raise ValueError("Alignment words require nonblank text and end >= start.")
        return self


class AlignmentResult(BaseModel):
    """Portable alignment occurrence, emitted only after complete validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime: RuntimeIdentity
    audio: AudioIdentity
    text: str
    language: str
    words: list[AlignmentWord] = Field(min_length=1)
    spoken_content_verified: Literal[False] = False
    timing_basis: Literal["qwen-forced-aligner-estimator-adjusted"] = "qwen-forced-aligner-estimator-adjusted"
    timing_diagnostics: None = None
    diagnostic_limit: str = "Upstream returns estimator-adjusted words, not raw timestamps or correction diagnostics."

    @model_validator(mode="after")
    def validate_timeline(self) -> Self:
        previous_end = 0.0
        for word in self.words:
            if word.start < previous_end or word.end > self.audio.duration_seconds + 0.001:
                raise ValueError("Alignment words overlap, are out of order, or exceed normalized audio duration.")
            previous_end = word.end
        return self
