"""Identity of source audio and the exact normalized waveform used by inference."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AudioIdentity(BaseModel):
    """Original file identity and the exact normalized array given to the model."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_dtype: Literal["<f4"] = "<f4"
    channels: Literal[1] = 1
    sample_rate: Literal[16000] = 16000
    duration_seconds: float = Field(gt=0)
    waveform_basis: Literal["ffmpeg-normalized-mono-pcm16-to-float32"] = "ffmpeg-normalized-mono-pcm16-to-float32"
