"""Voice synthesis workflows for preview and persisted renders."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voices import config
from voices.adapter.mlx_qwen import synthesize_reference_voice
from voices.adapter.model_snapshot import require_model_revision
from voices.domain.contracts import OutputDraft, VoiceRecord, require_optional_supported_language, require_voice_id
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
) -> PreparedSpeech:
    """Capture the immutable generation inputs before calling the runtime."""
    voice_id = require_voice_id(voice_id)
    language = require_optional_supported_language(language)
    expected_language = require_optional_supported_language(expected_language)
    model_id = config.BASE_MODEL
    revision = require_model_revision(config.BASE_MODEL_REVISION if model_revision is None else model_revision)
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
    runtime = get_runtime_identity()
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
    audio, sample_rate = synthesize_reference_voice(
        text=output_draft.text,
        language=resolved_language,
        reference_audio=assets.reference_audio,
        reference_text=assets.reference_text,
        model_id=model_id,
        model_revision=revision,
    )
    return PreparedSpeech(audio, sample_rate, assets.record, output_draft)


def synthesize_to_memory(
    *,
    voice_id: str,
    text: str,
    language: str | None,
    library: Path,
) -> tuple[np.ndarray, int, VoiceRecord]:
    """Return the immediate-playback projection over the same generation owner."""
    generated = prepare_speech(voice_id=voice_id, text=text, language=language, library=library)
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
    )
    return save_rendered_output(
        out_dir=out_dir,
        output_draft=generated.output_draft,
        audio_data=generated.audio,
        sample_rate=generated.sample_rate,
    )
