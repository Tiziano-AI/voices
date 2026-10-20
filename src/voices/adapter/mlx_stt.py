"""Typed adapter boundary around the local MLX speech-to-text runtime."""

import contextlib
import io

import numpy as np
from mlx_audio.stt.models.base import STTOutput
from mlx_audio.stt.models.qwen3_asr.qwen3_asr import Model as Qwen3AsrModel

from voices import config
from voices.adapter.mlx_runtime import serialized_mlx_runtime
from voices.adapter.model_snapshot import require_model_revision, resolve_model_snapshot
from voices.domain.create_contracts import TranscriptionDraft, TranscriptionSegment
from voices.domain.errors import GenerationError

_runtime_cache: dict[tuple[str, str], Qwen3AsrModel] = {}
MLX_RUNTIME_ERRORS = (OSError, RuntimeError, ValueError)


def _load_runtime(model_id: str, revision: str) -> Qwen3AsrModel:
    """Load one MLX STT runtime while suppressing upstream noise."""
    from mlx_audio.stt.utils import load as load_model

    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        runtime = load_model(resolve_model_snapshot(model_id, revision))
    if not isinstance(runtime, Qwen3AsrModel):
        raise GenerationError(f"Loaded runtime for '{model_id}' is not a Qwen3-ASR model.")
    return runtime


def _get_runtime(model_id: str, revision: str) -> Qwen3AsrModel:
    """Cache exact model and immutable-revision pairs under the MLX guard."""
    cache_key = (model_id, require_model_revision(revision))
    runtime = _runtime_cache.get(cache_key)
    if runtime is None:
        runtime = _load_runtime(*cache_key)
        _runtime_cache[cache_key] = runtime
    return runtime


def clear_runtime_cache() -> None:
    """Clear the process-local MLX STT runtime cache."""
    with serialized_mlx_runtime():
        _runtime_cache.clear()


def _segment_text(segment: dict[str, object]) -> str:
    """Extract one validated STT segment text field."""
    value = segment.get("text")
    if not isinstance(value, str):
        raise GenerationError("Speech-to-text returned a segment without text.")
    return value.strip()


def _segment_time(segment: dict[str, object], key: str) -> float:
    """Extract one validated STT segment time field."""
    value = segment.get(key)
    if isinstance(value, int | float):
        return float(value)
    raise GenerationError(f"Speech-to-text returned a segment without numeric {key}.")


def transcribe_audio(
    audio: np.ndarray,
    language: str,
    *,
    model_revision: str | None = None,
    model_id: str | None = None,
) -> TranscriptionDraft:
    """Transcribe normalized mono audio through the canonical STT model."""
    revision = require_model_revision(model_revision if model_revision is not None else config.STT_MODEL_REVISION)
    selected_model = model_id if model_id is not None else config.STT_MODEL
    try:
        with (
            serialized_mlx_runtime(),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            runtime = _get_runtime(selected_model, revision)
            result = runtime.generate(audio, language=language, verbose=False)
    except MLX_RUNTIME_ERRORS as exc:
        raise GenerationError(f"Speech-to-text generation failed: {exc}") from exc
    if not isinstance(result, STTOutput):
        raise GenerationError("Speech-to-text generation returned an unexpected result.")
    if not isinstance(result.text, str):
        raise GenerationError("Speech-to-text returned a non-text transcript.")
    transcript = result.text.strip()
    if not transcript:
        raise GenerationError("Speech-to-text returned no transcript.")
    duration_seconds = float(audio.shape[0]) / float(config.STT_SAMPLE_RATE)
    try:
        segments = [
            TranscriptionSegment(
                text=_segment_text(segment),
                language=language,
                start=_segment_time(segment, "start"),
                end=_segment_time(segment, "end"),
            )
            for segment in result.segments or []
        ]
        if not segments:
            segments = [
                TranscriptionSegment(
                    text=transcript,
                    language=language,
                    start=0.0,
                    end=duration_seconds,
                )
            ]
        return TranscriptionDraft(
            transcript=transcript,
            language=language,
            duration_seconds=duration_seconds,
            segments=segments,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise GenerationError(f"Speech-to-text returned an invalid transcription: {exc}") from exc
