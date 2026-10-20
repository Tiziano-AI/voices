"""Read-only supplied-text alignment with original and normalized audio identity."""

import hashlib
from importlib.util import find_spec
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from voices import config
from voices.adapter.ffmpeg_audio import convert_to_reference_audio
from voices.adapter.mlx_align import align_audio
from voices.adapter.model_snapshot import require_model_revision
from voices.domain.alignment_contracts import AlignmentResult
from voices.domain.audio_contracts import AudioIdentity
from voices.domain.contracts import require_non_empty_text, require_supported_language
from voices.domain.errors import AudioConversionError, GenerationError, InvalidInputError, MissingDependencyError
from voices.runtime_identity import get_runtime_identity


def _read_file(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise InvalidInputError(f"{label} must be an existing file: {path}")
        return path.read_bytes()
    except OSError as exc:
        raise InvalidInputError(f"Cannot read {label.lower()} '{path}': {exc}") from exc


def align_speech(*, audio: Path, text_file: Path, language: str, model_revision: str | None = None) -> AlignmentResult:
    """Validate ingress before loading a model; leave all source files untouched."""
    model_id = config.ALIGNER_MODEL
    revision = require_model_revision(model_revision if model_revision is not None else config.ALIGNER_MODEL_REVISION)
    language = require_supported_language(language)
    tokenizer = {"Japanese": "nagisa", "Korean": "soynlp"}.get(language)
    if tokenizer and find_spec(tokenizer) is None:
        raise MissingDependencyError(f"{language} forced alignment requires the optional '{tokenizer}' tokenizer.")
    try:
        text = _read_file(text_file, "Text file").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidInputError("Text file must contain UTF-8 text.") from exc
    require_non_empty_text("Text", text)
    source = audio.expanduser().resolve()
    source_hash = hashlib.sha256(_read_file(source, "Audio")).hexdigest()
    normalized = np.ascontiguousarray(
        convert_to_reference_audio(source, sample_rate=config.ALIGNER_SAMPLE_RATE), dtype="<f4"
    )
    if normalized.ndim != 1 or not normalized.size or not bool(np.isfinite(normalized).all()):
        raise AudioConversionError("Alignment requires nonempty, finite, normalized mono audio.")
    if hashlib.sha256(_read_file(source, "Audio")).hexdigest() != source_hash:
        raise InvalidInputError("Audio source changed during normalization; retry with a stable file.")
    audio_identity = AudioIdentity(
        path=str(source),
        sha256=source_hash,
        normalized_sha256=hashlib.sha256(normalized.tobytes(order="C")).hexdigest(),
        duration_seconds=normalized.size / config.ALIGNER_SAMPLE_RATE,
    )
    runtime = get_runtime_identity()
    words = align_audio(normalized, text, language, revision, model_id=model_id)
    try:
        return AlignmentResult(
            model_id=model_id,
            model_revision=revision,
            runtime=runtime,
            audio=audio_identity,
            text=text,
            language=language,
            words=words,
        )
    except ValidationError as exc:
        raise GenerationError(f"Forced alignment returned an invalid timeline: {exc}") from exc
