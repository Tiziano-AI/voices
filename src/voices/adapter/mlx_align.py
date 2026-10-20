"""Qwen ForcedAligner behind immutable selection and the process-global MLX lock."""

import contextlib
import io

import numpy as np
from mlx_audio.stt.models.qwen3_forced_aligner import ForcedAlignItem, ForcedAlignResult, Model

from voices.adapter.mlx_runtime import serialized_mlx_runtime
from voices.adapter.model_snapshot import require_model_revision, resolve_model_snapshot
from voices.domain.alignment_contracts import AlignmentWord
from voices.domain.errors import GenerationError, MissingDependencyError

_runtime_cache: dict[tuple[str, str], Model] = {}


def _load_runtime(model_id: str, revision: str) -> Model:
    from mlx_audio.stt.utils import load

    # The published snapshot's top-level model_type is qwen3_asr; its aligner
    # family is nested in thinker_config. Select the public loader family
    # explicitly rather than relying on ambiguous upstream name inference.
    runtime = load(resolve_model_snapshot(model_id, revision), strict=True, model_type="qwen3_forced_aligner")
    if not isinstance(runtime, Model):
        raise GenerationError(f"Loaded runtime for '{model_id}' is not a Qwen ForcedAligner model.")
    return runtime


def _get_runtime(model_id: str, revision: str) -> Model:
    key = (model_id, require_model_revision(revision))
    runtime = _runtime_cache.get(key)
    if runtime is None:
        runtime = _load_runtime(*key)
        _runtime_cache[key] = runtime
    return runtime


def clear_runtime_cache() -> None:
    """Retire cached models only while owning the shared MLX runtime."""
    with serialized_mlx_runtime():
        _runtime_cache.clear()


def align_audio(
    audio: np.ndarray, text: str, language: str, model_revision: str, *, model_id: str
) -> list[AlignmentWord]:
    """Return eager upstream estimates; no private timestamp monkeypatches."""
    try:
        with (
            serialized_mlx_runtime(),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            runtime = _get_runtime(model_id, model_revision)
            result = runtime.generate(audio=audio, text=text, language=language)
        if not isinstance(result, ForcedAlignResult):
            raise GenerationError("Forced alignment returned an unexpected result.")
        if not result.items:
            raise GenerationError("Forced alignment returned no words.")
        if any(not isinstance(item, ForcedAlignItem) for item in result.items):
            raise GenerationError("Forced alignment returned an unexpected word item.")
        return [AlignmentWord(text=item.text, start=item.start_time, end=item.end_time) for item in result.items]
    except ImportError as exc:
        raise MissingDependencyError(f"Forced alignment dependency is unavailable: {exc}") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise GenerationError(f"Forced alignment failed: {exc}") from exc
