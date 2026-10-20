import pytest
from pydantic import ValidationError

from voices.domain.create_contracts import (
    GUIDED_RECORDING_SCRIPTS,
    CloneReviewRequest,
    get_guided_recording_script,
)


def test_guided_recording_scripts_are_rich_clone_prompts():
    sentence_marks = ".?!。！？"
    question_marks = "?？"

    assert set(GUIDED_RECORDING_SCRIPTS) == {
        "Chinese",
        "English",
        "French",
        "German",
        "Italian",
        "Japanese",
        "Korean",
        "Portuguese",
        "Russian",
        "Spanish",
    }
    for script in GUIDED_RECORDING_SCRIPTS.values():
        visible_length = len(script.replace(" ", ""))
        sentence_count = sum(script.count(mark) for mark in sentence_marks)
        has_question_turn = any(mark in script for mark in question_marks)
        assert visible_length >= 120
        assert sentence_count >= 4
        assert has_question_turn


def test_guided_recording_script_requires_supported_language():
    with pytest.raises(ValueError, match="language must be one of"):
        get_guided_recording_script("Auto")


def test_clone_review_request_accepts_record_free_policy():
    request = CloneReviewRequest(
        language="english",
        review_policy="record_free",
        fallback_name="Stage Voice",
    )

    assert request.language == "English"
    assert request.review_policy == "record_free"


def test_clone_review_request_rejects_invalid_voice_id():
    with pytest.raises(ValidationError, match=r"voice id must match"):
        CloneReviewRequest(
            language="English",
            review_policy="import",
            requested_voice_id="foo/bar",
            fallback_name="Stage Voice",
        )
