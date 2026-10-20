"""Reference voice creation workflows for design generation and prompt batches."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voices import config
from voices.adapter.mlx_qwen import design_reference_audio
from voices.domain.contracts import (
    DesignPromptInput,
    DesignVoiceSource,
    VoiceDraft,
    VoiceRecord,
    require_non_empty_text,
    require_supported_language,
    require_voice_id,
)
from voices.domain.errors import VoiceAlreadyExistsError, VoicesError
from voices.store.library_store import save_voice_record, voice_exists
from voices.util.slug import display_name_from_voice_id
from voices.util.timestamps import utc_now


@dataclass(frozen=True, slots=True)
class PreparedDesignedVoice:
    """Generated design audio plus metadata awaiting the final persistence gate."""

    voice_draft: VoiceDraft
    audio_data: np.ndarray
    sample_rate: int


def prepare_designed_voice(
    *,
    voice_id: str,
    name: str | None,
    instruct: str,
    text: str,
    language: str,
    library: Path,
    overwrite: bool,
) -> PreparedDesignedVoice:
    """Generate one VoiceDesign reference without writing it to the durable library."""
    voice_id = require_voice_id(voice_id)
    language = require_supported_language(language)
    instruct = require_non_empty_text("voice design prompt", instruct)
    text = require_non_empty_text("reference text", text)
    if voice_exists(library, voice_id) and not overwrite:
        raise VoiceAlreadyExistsError(f"Voice '{voice_id}' already exists. Use --overwrite to replace.")
    source = DesignVoiceSource(
        kind="design",
        model_id=config.VOICE_DESIGN_MODEL,
        instruct=instruct,
    )
    voice_draft = VoiceDraft(
        id=voice_id,
        name=name or display_name_from_voice_id(voice_id),
        created_at=utc_now(),
        language=language,
        base_model_id=config.BASE_MODEL,
        reference_text=text,
        source=source,
    )
    audio_data, sample_rate = design_reference_audio(
        text=voice_draft.reference_text,
        instruct=source.instruct,
        language=voice_draft.language,
    )
    return PreparedDesignedVoice(voice_draft=voice_draft, audio_data=audio_data, sample_rate=sample_rate)


def save_prepared_designed_voice(
    *,
    library: Path,
    prepared: PreparedDesignedVoice,
    overwrite: bool,
) -> VoiceRecord:
    """Persist a prepared design voice after the caller's final cancellation gate."""
    return save_voice_record(
        library=library,
        voice_draft=prepared.voice_draft,
        audio_data=prepared.audio_data,
        sample_rate=prepared.sample_rate,
        overwrite=overwrite,
    )


def create_designed_voice(
    *,
    voice_id: str,
    name: str | None,
    instruct: str,
    text: str,
    language: str,
    library: Path,
    overwrite: bool,
) -> VoiceRecord:
    """Create and persist one VoiceDesign-generated reference voice."""
    prepared = prepare_designed_voice(
        voice_id=voice_id,
        name=name,
        instruct=instruct,
        text=text,
        language=language,
        library=library,
        overwrite=overwrite,
    )
    return save_prepared_designed_voice(library=library, prepared=prepared, overwrite=overwrite)


def create_voice_batch(
    *,
    prompts: list[DesignPromptInput],
    default_text: str | None,
    default_language: str,
    library: Path,
    overwrite: bool,
) -> tuple[list[VoiceRecord], list[tuple[str, str]]]:
    """Create a batch of designed voices while continuing past recoverable failures."""
    successes: list[VoiceRecord] = []
    failures: list[tuple[str, str]] = []
    for prompt in prompts:
        text = prompt.text or default_text
        if text is None:
            failures.append((prompt.id, "No seed text provided."))
            continue
        try:
            successes.append(
                create_designed_voice(
                    voice_id=prompt.id,
                    name=prompt.name or None,
                    instruct=prompt.instruct,
                    text=text,
                    language=prompt.language or default_language,
                    library=library,
                    overwrite=overwrite,
                )
            )
        except VoicesError as exc:
            failures.append((prompt.id, str(exc)))
    return successes, failures
