import pytest
from pydantic import ValidationError

from voices import config
from voices.domain.contracts import (
    DesignPromptInput,
    OutputDraft,
    VoiceDraft,
    require_optional_supported_language,
    require_supported_language,
    require_voice_id,
)
from voices.domain.errors import InvalidInputError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("test_voice", "test_voice"),
        ("test-voice", "test-voice"),
        ("voice01", "voice01"),
    ],
)
def test_require_voice_id_accepts_strict_slugs(value, expected):
    assert require_voice_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [".", "..", "Bad-ID", "foo/bar", r"foo\bar", "foo.bar", "foo bar", "_foo", "foo_", "foo--bar", "foo__bar"],
)
def test_require_voice_id_rejects_invalid_shapes(value):
    with pytest.raises(InvalidInputError, match=r"voice id must match"):
        require_voice_id(value)


@pytest.mark.parametrize("value", ["Chinese", "english", "ITALIAN", " Portuguese "])
def test_require_supported_language_normalizes_known_languages(value):
    assert require_supported_language(value) in {
        "Chinese",
        "English",
        "Italian",
        "Portuguese",
    }


def test_require_supported_language_rejects_unknown_language():
    with pytest.raises(InvalidInputError, match="language must be one of"):
        require_supported_language("Auto")


def test_require_optional_supported_language_preserves_none():
    assert require_optional_supported_language(None) is None


def test_voice_draft_rejects_unsupported_language():
    with pytest.raises(ValidationError, match="language must be one of"):
        VoiceDraft(
            id="test_voice",
            name="Test Voice",
            created_at="2026-04-08T12:00:00Z",
            language="Auto",
            base_model_id=config.BASE_MODEL,
            reference_text="Hello world.",
            source={"kind": "clone"},
        )


def test_output_draft_rejects_invalid_reference_voice_id():
    with pytest.raises(ValidationError, match=r"voice id must match"):
        OutputDraft(
            voice_id="test_voice",
            created_at="2026-04-08T12:00:00Z",
            language="English",
            base_model_id=config.BASE_MODEL,
            text="Hello world.",
            reference_voice_id="foo/bar",
            reference_sha256="a" * 64,
        )


def test_design_prompt_rejects_unsupported_language():
    with pytest.raises(ValidationError, match="language must be one of"):
        DesignPromptInput.model_validate(
            {
                "id": "test_voice",
                "instruct": "Low narrator",
                "text": "Hello world.",
                "language": "Auto",
            }
        )
