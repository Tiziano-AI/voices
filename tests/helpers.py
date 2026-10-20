from pathlib import Path

import numpy as np

from voices import config
from voices.domain.contracts import (
    ClonedVoiceSource,
    DesignVoiceSource,
    VoiceDraft,
    VoiceRecord,
)
from voices.store.library_store import save_voice_record

MOCK_AUDIO = np.zeros(2400, dtype=np.float32)
LONG_MOCK_AUDIO = np.zeros(96000, dtype=np.float32)


def make_design_draft(
    voice_id: str = "test_voice",
    *,
    name: str = "Test Voice",
    created_at: str = "2026-04-08T12:00:00Z",
    language: str = "English",
    instruct: str = "Low narrator",
    reference_text: str = "Hello world.",
) -> VoiceDraft:
    return VoiceDraft(
        id=voice_id,
        name=name,
        created_at=created_at,
        language=language,
        base_model_id=config.BASE_MODEL,
        reference_text=reference_text,
        source=DesignVoiceSource(
            kind="design",
            model_id=config.VOICE_DESIGN_MODEL,
            instruct=instruct,
        ),
    )


def make_clone_draft(
    voice_id: str = "test_voice",
    *,
    name: str = "Test Voice",
    created_at: str = "2026-04-08T12:00:00Z",
    language: str = "English",
    reference_text: str = "Hello world.",
) -> VoiceDraft:
    return VoiceDraft(
        id=voice_id,
        name=name,
        created_at=created_at,
        language=language,
        base_model_id=config.BASE_MODEL,
        reference_text=reference_text,
        source=ClonedVoiceSource(kind="clone"),
    )


def make_design_record(voice_id: str = "test_voice") -> VoiceRecord:
    return VoiceRecord(
        schema_version=2,
        id=voice_id,
        name="Test Voice",
        created_at="2026-04-08T12:00:00Z",
        language="English",
        base_model_id=config.BASE_MODEL,
        reference_text="Hello world.",
        reference_sha256="a" * 64,
        source=DesignVoiceSource(
            kind="design",
            model_id=config.VOICE_DESIGN_MODEL,
            instruct="Low narrator",
        ),
    )


def seed_voice(lib: Path, voice_id: str = "test_voice") -> VoiceRecord:
    """Create a design voice on disk without invoking a model."""
    return save_voice_record(lib, make_design_draft(voice_id), MOCK_AUDIO, 24000)


def seed_clone_voice(lib: Path, voice_id: str = "test_voice") -> VoiceRecord:
    """Create a cloned voice on disk without invoking ffmpeg."""
    return save_voice_record(lib, make_clone_draft(voice_id), MOCK_AUDIO, 24000)
