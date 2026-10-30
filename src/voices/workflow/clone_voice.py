"""Clone voice workflows for imported and recorded reference audio."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voices import config
from voices.adapter.dgx_compute import execute
from voices.adapter.ffmpeg_audio import convert_to_reference_audio
from voices.adapter.mlx_stt import transcribe_audio
from voices.compute import LOCAL_COMPUTE, ComputeSelection
from voices.domain.contracts import (
    ClonedVoiceSource,
    VoiceDraft,
    VoiceRecord,
    require_non_empty_text,
    require_supported_language,
    require_voice_id,
)
from voices.domain.create_contracts import CloneReviewRequest, TranscriptionDraft, TranscriptionSegment
from voices.domain.errors import AudioConversionError, InvalidInputError, VoiceAlreadyExistsError
from voices.store.library_store import save_voice_record, voice_exists
from voices.util.slug import display_name_from_voice_id, voice_id_from_name
from voices.util.timestamps import utc_now


@dataclass(frozen=True, slots=True)
class PreparedCloneReview:
    """Canonical post-capture review payload shared by clone and record paths."""

    draft: TranscriptionDraft
    normalized_audio: np.ndarray
    suggested_voice_id: str


def _review_draft_from_transcript(transcript: str, language: str, duration_seconds: float) -> TranscriptionDraft:
    """Build one review draft when the transcript is already approved."""
    return TranscriptionDraft(
        transcript=transcript,
        language=language,
        duration_seconds=duration_seconds,
        segments=[
            TranscriptionSegment(
                text=transcript,
                language=language,
                start=0.0,
                end=duration_seconds,
            )
        ],
    )


def _minimum_duration_seconds(review_policy: str) -> float | None:
    """Resolve the product minimum duration for one review policy."""
    if review_policy == "record_free":
        return config.FREE_RECORD_MINIMUM_SECONDS
    return None


def _require_decoded_audio(audio: np.ndarray) -> np.ndarray:
    """Reject normalized clone audio that contains no samples."""
    if audio.size == 0:
        raise AudioConversionError("Reference audio contains no decodable samples.")
    return audio


def clone_reference_voice(
    *,
    voice_id: str,
    name: str | None,
    audio_path: Path,
    transcript: str,
    language: str,
    library: Path,
    overwrite: bool,
) -> VoiceRecord:
    """Create and persist one cloned reference voice from imported or recorded audio."""
    voice_id = require_voice_id(voice_id)
    language = require_supported_language(language)
    transcript = require_non_empty_text("reference text", transcript)
    if voice_exists(library, voice_id) and not overwrite:
        raise VoiceAlreadyExistsError(f"Voice '{voice_id}' already exists. Use --overwrite to replace.")
    voice_draft = VoiceDraft(
        id=voice_id,
        name=name or display_name_from_voice_id(voice_id),
        created_at=utc_now(),
        language=language,
        base_model_id=config.BASE_MODEL,
        reference_text=transcript,
        source=ClonedVoiceSource(kind="clone"),
    )
    audio = _require_decoded_audio(convert_to_reference_audio(audio_path, config.FALLBACK_SAMPLE_RATE))
    return save_voice_record(
        library=library,
        voice_draft=voice_draft,
        audio_data=audio,
        sample_rate=config.FALLBACK_SAMPLE_RATE,
        overwrite=overwrite,
    )


def transcribe_clone_audio(
    *,
    audio_path: Path,
    language: str,
    compute: ComputeSelection = LOCAL_COMPUTE,
) -> TranscriptionDraft:
    """Transcribe one clone reference candidate through the canonical STT path."""
    resolved_language = require_supported_language(language)
    normalized_audio = _require_decoded_audio(convert_to_reference_audio(audio_path, config.STT_SAMPLE_RATE))
    if compute.backend == "dgx":
        result = execute(
            compute,
            "asr",
            language=resolved_language,
            audio=normalized_audio.astype("<f4").tobytes(),
            audio_format="f32le-16000",
        )
        duration = float(normalized_audio.size) / config.STT_SAMPLE_RATE
        return _review_draft_from_transcript(result.payload["transcript"], resolved_language, duration)
    return transcribe_audio(normalized_audio, resolved_language)


def measure_clone_audio_duration(audio_path: Path) -> float:
    """Return the normalized duration for one imported or recorded clone candidate."""
    normalized_audio = _require_decoded_audio(convert_to_reference_audio(audio_path, config.STT_SAMPLE_RATE))
    return float(normalized_audio.shape[0]) / float(config.STT_SAMPLE_RATE)


def suggest_voice_id(library: Path, name: str) -> str:
    """Return the first available strict voice id derived from a display name."""
    base_id = voice_id_from_name(name)
    candidate = base_id
    suffix = 2
    while voice_exists(library, candidate):
        candidate = f"{base_id}-{suffix}"
        suffix += 1
    return candidate


def prepare_clone_review(
    *,
    audio_path: Path,
    library: Path,
    request: CloneReviewRequest,
    compute: ComputeSelection = LOCAL_COMPUTE,
) -> PreparedCloneReview:
    """Normalize one imported or recorded clip and project the canonical review payload."""
    normalized_audio = _require_decoded_audio(convert_to_reference_audio(audio_path, config.FALLBACK_SAMPLE_RATE))
    duration_seconds = float(normalized_audio.shape[0]) / float(config.FALLBACK_SAMPLE_RATE)
    minimum_duration_seconds = _minimum_duration_seconds(request.review_policy)
    if minimum_duration_seconds is not None and duration_seconds < minimum_duration_seconds:
        raise InvalidInputError(
            f"Recorded take must be at least {minimum_duration_seconds:.0f}s before transcript review."
        )
    if request.transcript is None:
        draft = transcribe_clone_audio(audio_path=audio_path, language=request.language, compute=compute)
    else:
        draft = _review_draft_from_transcript(request.transcript, request.language, duration_seconds)
    requested_name = request.requested_name or request.fallback_name
    suggested_voice_id = request.requested_voice_id or suggest_voice_id(library, requested_name)
    return PreparedCloneReview(
        draft=draft,
        normalized_audio=normalized_audio,
        suggested_voice_id=suggested_voice_id,
    )
