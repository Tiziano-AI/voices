"""Voice synthesis workflows for preview and persisted renders."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voices.adapter.dgx_compute import execute
from voices.adapter.mlx_qwen import synthesize_reference_voice
from voices.adapter.model_snapshot import require_model_revision
from voices.compute import LOCAL_COMPUTE, ComputeSelection
from voices.domain.contracts import (
    OutputDraft,
    VoiceRecord,
    require_non_empty_text,
    require_optional_supported_language,
    require_voice_id,
)
from voices.domain.errors import InputConflictError
from voices.domain.speech_contracts import SpeechModelIdentity, SpeechReferenceIdentity
from voices.runtime_identity import get_runtime_identity
from voices.store.library_store import load_voice_snapshot
from voices.store.output_store import save_rendered_output
from voices.util.timestamps import utc_now


@dataclass(frozen=True, slots=True)
class PreparedSpeech:
    """Generation output bound to the model selection and runtime used for it."""

    audio: np.ndarray
    sample_rate: int
    voice: VoiceRecord
    output_draft: OutputDraft


def prepare_speech(
    *,
    voice_id: str,
    text: str,
    language: str | None,
    library: Path,
    model_revision: str | None = None,
    expected_reference: SpeechReferenceIdentity | None = None,
    expected_model: SpeechModelIdentity | None = None,
    expected_language: str | None = None,
    compute: ComputeSelection = LOCAL_COMPUTE,
) -> PreparedSpeech:
    """Capture the immutable generation inputs before calling the runtime."""
    voice_id = require_voice_id(voice_id)
    text = require_non_empty_text("text", text)
    language = require_optional_supported_language(language)
    expected_language = require_optional_supported_language(expected_language)
    model_id, selected_revision = compute.model("base", model_revision)
    revision = require_model_revision(selected_revision)
    assets = load_voice_snapshot(library, voice_id)
    reference = SpeechReferenceIdentity(
        reference_sha256=assets.record.reference_sha256, reference_text_sha256=assets.reference_text_sha256
    )
    model = SpeechModelIdentity(base_model_id=model_id, base_model_revision=revision)
    if expected_reference is not None and reference != expected_reference:
        raise InputConflictError("The reference changed. Refresh the voice library before retrying.")
    if expected_model is not None and model != expected_model:
        raise InputConflictError("The model changed. Refresh the model selection before retrying.")
    resolved_language = language or assets.record.language
    if expected_language is not None and resolved_language != expected_language:
        raise InputConflictError("The language changed. Refresh the voice library before retrying.")
    if compute.backend == "dgx":
        result = execute(
            compute,
            "base",
            text=text,
            language=resolved_language,
            audio=assets.reference_audio,
            audio_format="wav",
            reference_text=assets.reference_text,
            revision=revision,
        )
        if result.audio is None or result.sample_rate is None:
            raise InputConflictError("DGX synthesis did not return complete audio.")
        audio, sample_rate, runtime = result.audio, result.sample_rate, result.runtime
    else:
        runtime = get_runtime_identity()
        audio, sample_rate = synthesize_reference_voice(
            text=text,
            language=resolved_language,
            reference_audio=assets.reference_audio,
            reference_text=assets.reference_text,
            model_id=model_id,
            model_revision=revision,
        )
    output_draft = OutputDraft(
        voice_id=voice_id,
        created_at=utc_now(),
        language=resolved_language,
        base_model_id=model_id,
        base_model_revision=revision,
        runtime=runtime,
        text=text,
        reference_voice_id=voice_id,
        reference_sha256=assets.record.reference_sha256,
        reference_text_sha256=assets.reference_text_sha256,
    )
    return PreparedSpeech(audio, sample_rate, assets.record, output_draft)


def synthesize_to_memory(
    *,
    voice_id: str,
    text: str,
    language: str | None,
    library: Path,
    compute: ComputeSelection = LOCAL_COMPUTE,
) -> tuple[np.ndarray, int, VoiceRecord]:
    """Return the immediate-playback projection over the same generation owner."""
    generated = prepare_speech(voice_id=voice_id, text=text, language=language, library=library, compute=compute)
    return generated.audio, generated.sample_rate, generated.voice


def render_speech(
    *,
    voice_id: str,
    text: str,
    language: str | None,
    library: Path,
    out_dir: Path,
    model_revision: str | None = None,
    expected_reference: SpeechReferenceIdentity | None = None,
    expected_model: SpeechModelIdentity | None = None,
    compute: ComputeSelection = LOCAL_COMPUTE,
) -> Path:
    """Generate speech and persist the WAV plus schema v2 sidecar."""
    voice_id = require_voice_id(voice_id)
    language = require_optional_supported_language(language)
    generated = prepare_speech(
        voice_id=voice_id,
        text=text,
        language=language,
        library=library,
        model_revision=model_revision,
        expected_reference=expected_reference,
        expected_model=expected_model,
        compute=compute,
    )
    return save_rendered_output(
        out_dir=out_dir,
        output_draft=generated.output_draft,
        audio_data=generated.audio,
        sample_rate=generated.sample_rate,
    )
