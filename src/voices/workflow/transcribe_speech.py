"""Transcribe an existing WAV without recording, playback or library mutation."""

import hashlib
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from voices import config
from voices.adapter.ffmpeg_audio import convert_to_reference_audio
from voices.adapter.mlx_stt import transcribe_audio
from voices.adapter.model_snapshot import require_model_revision
from voices.domain.audio_contracts import AudioIdentity
from voices.domain.contracts import require_supported_language
from voices.domain.errors import AudioConversionError, GenerationError, InvalidInputError
from voices.domain.transcription_contracts import TranscriptionResult
from voices.runtime_identity import get_runtime_identity


def _read_wav(path: Path) -> bytes:
    """Check the actual WAV container before any model work, not its filename."""
    try:
        if not path.is_file():
            raise InvalidInputError(f"Audio must be an existing WAV file: {path}")
        content = path.read_bytes()
    except OSError as exc:
        raise InvalidInputError(f"Cannot read audio '{path}': {exc}") from exc
    if content[:4] not in (b"RIFF", b"RIFX", b"RF64") or content[8:12] != b"WAVE":
        raise InvalidInputError(f"Audio must be a WAV container: {path}")
    return content


def transcribe_speech(*, audio: Path, language: str, model_revision: str) -> TranscriptionResult:
    """Recognize audio only; return provenance and leave source files untouched."""
    model_id = config.STT_MODEL
    revision = require_model_revision(model_revision)
    language = require_supported_language(language)
    try:
        source = audio.expanduser().resolve()
    except OSError as exc:
        raise InvalidInputError(f"Cannot resolve audio '{audio}': {exc}") from exc
    source_hash = hashlib.sha256(_read_wav(source)).hexdigest()
    normalized = np.ascontiguousarray(
        convert_to_reference_audio(source, sample_rate=config.STT_SAMPLE_RATE), dtype="<f4"
    )
    if normalized.ndim != 1 or not normalized.size or not bool(np.isfinite(normalized).all()):
        raise AudioConversionError("Transcription requires nonempty, finite, normalized mono audio.")
    if hashlib.sha256(_read_wav(source)).hexdigest() != source_hash:
        raise InvalidInputError("Audio source changed during normalization; retry with a stable file.")
    audio_identity = AudioIdentity(
        path=str(source),
        sha256=source_hash,
        normalized_sha256=hashlib.sha256(normalized.tobytes(order="C")).hexdigest(),
        duration_seconds=normalized.size / config.STT_SAMPLE_RATE,
    )
    runtime = get_runtime_identity()
    draft = transcribe_audio(normalized, language, model_revision=revision, model_id=model_id)
    try:
        return TranscriptionResult(
            transcript=draft.transcript,
            language=language,
            model_id=model_id,
            model_revision=revision,
            runtime=runtime,
            audio=audio_identity,
        )
    except ValidationError as exc:
        raise GenerationError(f"Speech-to-text returned an invalid transcript: {exc}") from exc
