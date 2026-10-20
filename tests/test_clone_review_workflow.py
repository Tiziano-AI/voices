from unittest.mock import patch

import numpy as np
import pytest

from voices.domain.create_contracts import CloneReviewRequest
from voices.domain.errors import AudioConversionError, InvalidInputError
from voices.workflow.clone_voice import prepare_clone_review


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=np.zeros(24000, dtype=np.float32))
def test_prepare_clone_review_uses_supplied_transcript_without_stt(mock_convert, tmp_path):
    review = prepare_clone_review(
        audio_path=tmp_path / "source.wav",
        library=tmp_path / "voices",
        request=CloneReviewRequest(
            language="English",
            review_policy="import",
            transcript="Approved transcript.",
            fallback_name="Stage Voice",
        ),
    )

    assert review.draft.transcript == "Approved transcript."
    assert review.draft.duration_seconds == 1.0
    assert review.suggested_voice_id == "stage-voice"
    mock_convert.assert_called_once_with(tmp_path / "source.wav", 24000)


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=np.array([], dtype=np.float32))
def test_prepare_clone_review_rejects_empty_decoded_audio(mock_convert, tmp_path):
    with pytest.raises(AudioConversionError, match="no decodable samples"):
        prepare_clone_review(
            audio_path=tmp_path / "source.wav",
            library=tmp_path / "voices",
            request=CloneReviewRequest(
                language="English",
                review_policy="import",
                transcript="Approved transcript.",
                fallback_name="Stage Voice",
            ),
        )

    mock_convert.assert_called_once_with(tmp_path / "source.wav", 24000)


@patch("voices.workflow.clone_voice.transcribe_clone_audio")
@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=np.zeros(2400, dtype=np.float32))
def test_prepare_clone_review_rejects_short_free_record_before_stt(mock_convert, mock_transcribe, tmp_path):
    with pytest.raises(InvalidInputError, match="at least 3s"):
        prepare_clone_review(
            audio_path=tmp_path / "source.wav",
            library=tmp_path / "voices",
            request=CloneReviewRequest(
                language="English",
                review_policy="record_free",
                fallback_name="Stage Voice",
            ),
        )

    mock_convert.assert_called_once_with(tmp_path / "source.wav", 24000)
    mock_transcribe.assert_not_called()
