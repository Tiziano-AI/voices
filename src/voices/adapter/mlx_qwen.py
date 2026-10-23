"""Typed adapter boundary around the mlx-audio Qwen3-TTS runtime."""

import contextlib
import io
import logging
import os
from collections.abc import Iterable

import mlx.core as mx
import numpy as np
from mlx_audio.audio_io import read as read_audio
from mlx_audio.tts.models.base import GenerationResult
from mlx_audio.tts.models.qwen3_tts.qwen3_tts import Model as Qwen3TtsModel

from voices import config
from voices.adapter.mlx_runtime import serialized_mlx_runtime
from voices.adapter.model_snapshot import require_model_revision, resolve_model_snapshot
from voices.domain.errors import GenerationError

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


_runtime_cache: dict[tuple[str, str], Qwen3TtsModel] = {}
MLX_RUNTIME_ERRORS = (OSError, RuntimeError, ValueError)


def _load_runtime(model_id: str, revision: str) -> Qwen3TtsModel:
    """Load one MLX Qwen runtime while suppressing known upstream noise."""
    from mlx_audio.tts.utils import load_model

    config_logger = logging.getLogger("transformers.configuration_utils")
    previous_level = config_logger.level
    config_logger.setLevel(logging.ERROR)
    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            runtime = load_model(resolve_model_snapshot(model_id, revision))
    finally:
        config_logger.setLevel(previous_level)
    if not isinstance(runtime, Qwen3TtsModel):
        raise GenerationError(f"Loaded runtime for '{model_id}' is not a Qwen3-TTS model.")
    return runtime


def _get_runtime(model_id: str, revision: str) -> Qwen3TtsModel:
    """Cache only exact model and immutable-revision pairs, while holding MLX."""
    cache_key = (model_id, require_model_revision(revision))
    runtime = _runtime_cache.get(cache_key)
    if runtime is None:
        runtime = _load_runtime(*cache_key)
        _runtime_cache[cache_key] = runtime
    return runtime


def clear_runtime_cache() -> None:
    """Clear the process-local MLX runtime cache."""
    with serialized_mlx_runtime():
        _runtime_cache.clear()


def _collect_audio(
    chunks: Iterable[GenerationResult],
    empty_message: str,
) -> np.ndarray:
    """Retain every chunk and finish upstream cleanup before releasing MLX."""
    # Qwen generators perform runtime cleanup after their final yield, even
    # for non-streaming single-clip generation. Exhaust them under the lock.
    audio_chunks = [np.array(chunk.audio, dtype=np.float32) for chunk in chunks]
    if not audio_chunks or any(audio.size == 0 for audio in audio_chunks):
        raise GenerationError(empty_message)
    return np.concatenate(audio_chunks)


def design_reference_audio(
    text: str,
    instruct: str,
    language: str,
) -> tuple[np.ndarray, int]:
    """Generate a new reference clip through the VoiceDesign model."""
    try:
        with serialized_mlx_runtime():
            runtime = _get_runtime(config.VOICE_DESIGN_MODEL, config.VOICE_DESIGN_MODEL_REVISION)
            audio = _collect_audio(
                runtime.generate_voice_design(
                    text=text,
                    instruct=instruct,
                    language=language,
                    verbose=False,
                ),
                "VoiceDesign returned no audio.",
            )
    except MLX_RUNTIME_ERRORS as exc:
        raise GenerationError(f"VoiceDesign generation failed: {exc}") from exc
    return audio, int(runtime.sample_rate)


def synthesize_reference_voice(
    text: str,
    language: str,
    reference_audio: bytes,
    reference_text: str,
    *,
    model_id: str | None = None,
    model_revision: str | None = None,
) -> tuple[np.ndarray, int]:
    """Generate speech from text using a saved reference voice."""
    selected_model = config.BASE_MODEL if model_id is None else model_id
    revision = require_model_revision(config.BASE_MODEL_REVISION if model_revision is None else model_revision)
    try:
        with serialized_mlx_runtime():
            runtime = _get_runtime(selected_model, revision)
            samples, _ = read_audio(
                io.BytesIO(reference_audio), dtype="float32", sample_rate=int(runtime.sample_rate), nchannels=1
            )
            # mlx-audio 0.6.1 keys this private cache by sample count and sum,
            # which collide for different references. Retain loaded model weights,
            # never its lossy reference-code identity across our operations.
            runtime._icl_cache.clear()
            audio = _collect_audio(
                runtime.generate(
                    text=text,
                    ref_audio=mx.array(samples, dtype=mx.float32),
                    ref_text=reference_text,
                    lang_code=language,
                    verbose=False,
                ),
                "Base model returned no audio.",
            )
    except MLX_RUNTIME_ERRORS as exc:
        raise GenerationError(f"Base generation failed: {exc}") from exc
    return audio, int(runtime.sample_rate)
