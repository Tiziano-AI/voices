from unittest.mock import MagicMock

import pytest
from helpers import MOCK_AUDIO
from mlx_audio.stt.models.base import STTOutput

from voices.adapter import mlx_stt
from voices.domain.errors import GenerationError


def test_transcribe_audio_maps_segments(monkeypatch):
    runtime = MagicMock()
    runtime.generate.return_value = STTOutput(
        text="Hello there.",
        segments=[{"text": "Hello there.", "start": 0.0, "end": 0.1}],
        language="English",
    )
    monkeypatch.setattr(mlx_stt, "_get_runtime", lambda cache_key, model_id: runtime)

    draft = mlx_stt.transcribe_audio(MOCK_AUDIO, "English")

    assert draft.transcript == "Hello there."
    assert draft.language == "English"
    assert draft.segments[0].text == "Hello there."
    runtime.generate.assert_called_once_with(MOCK_AUDIO, language="English", verbose=False)


def test_transcribe_audio_falls_back_to_one_segment(monkeypatch):
    runtime = MagicMock()
    runtime.generate.return_value = STTOutput(text="Hello there.", segments=[], language="English")
    monkeypatch.setattr(mlx_stt, "_get_runtime", lambda cache_key, model_id: runtime)

    draft = mlx_stt.transcribe_audio(MOCK_AUDIO, "English")

    assert len(draft.segments) == 1
    assert draft.segments[0].text == "Hello there."


def test_transcribe_audio_raises_on_empty_transcript(monkeypatch):
    runtime = MagicMock()
    runtime.generate.return_value = STTOutput(text="   ", segments=[], language="English")
    monkeypatch.setattr(mlx_stt, "_get_runtime", lambda cache_key, model_id: runtime)

    with pytest.raises(GenerationError, match="returned no transcript"):
        mlx_stt.transcribe_audio(MOCK_AUDIO, "English")


def test_transcribe_audio_wraps_runtime_error(monkeypatch):
    runtime = MagicMock()
    runtime.generate.side_effect = RuntimeError("metal failed")
    monkeypatch.setattr(mlx_stt, "_get_runtime", lambda cache_key, model_id: runtime)

    with pytest.raises(GenerationError, match="Speech-to-text generation failed"):
        mlx_stt.transcribe_audio(MOCK_AUDIO, "English")
