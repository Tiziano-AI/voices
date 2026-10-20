import json
from unittest.mock import patch

from helpers import MOCK_AUDIO
from typer.testing import CliRunner

from voices.cli import app
from voices.domain.create_contracts import TranscriptionDraft
from voices.domain.errors import InvalidInputError
from voices.workflow.clone_voice import PreparedCloneReview

runner = CliRunner()


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_review_and_save_create_voice(mock_convert, tmp_path):
    lib = tmp_path / "voices"
    audio_file = tmp_path / "recording.wav"
    review_file = tmp_path / "reviews" / "matteo-review.json"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    review_result = runner.invoke(
        app,
        [
            "--json",
            "clone",
            "review",
            "--audio",
            str(audio_file),
            "--transcript",
            "Hello from the recording.",
            "--language",
            "Italian",
            "--name",
            "Cloned Voice",
            "--voice-id",
            "cloned_voice",
            "--review-out",
            str(review_file),
            "--library",
            str(lib),
        ],
    )
    assert review_result.exit_code == 0, review_result.output
    review_payload = json.loads(review_result.output)
    assert review_payload["review"]["suggested_voice_id"] == "cloned_voice"
    assert review_file.exists()
    assert review_file.with_suffix(".wav").exists()

    save_result = runner.invoke(
        app,
        [
            "--json",
            "clone",
            "save",
            "--review",
            str(review_file),
            "--id",
            "cloned_voice",
            "--name",
            "Cloned Voice",
            "--library",
            str(lib),
        ],
    )

    assert save_result.exit_code == 0, save_result.output
    save_payload = json.loads(save_result.output)
    assert save_payload["voice"]["id"] == "cloned_voice"
    voice_json = (lib / "cloned_voice" / "voice.json").read_text(encoding="utf-8")
    assert '"kind": "clone"' in voice_json
    assert '"language": "Italian"' in voice_json
    assert '"reference_text": "Hello from the recording."' in voice_json
    assert "design_model" not in voice_json
    assert mock_convert.call_count == 2


def test_clone_review_missing_audio_exits_2(tmp_path):
    result = runner.invoke(
        app,
        [
            "--json",
            "clone",
            "review",
            "--audio",
            str(tmp_path / "nonexistent.mp3"),
            "--transcript",
            "x",
            "--review-out",
            str(tmp_path / "review.json"),
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "invalid_input"


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_review_rejects_blank_transcript_before_conversion(mock_convert, tmp_path):
    audio_file = tmp_path / "rec.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    result = runner.invoke(
        app,
        [
            "clone",
            "review",
            "--audio",
            str(audio_file),
            "--transcript",
            "   ",
            "--review-out",
            str(tmp_path / "review.json"),
        ],
    )

    assert result.exit_code == 2
    mock_convert.assert_not_called()


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_review_rejects_blank_name_before_conversion(mock_convert, tmp_path):
    audio_file = tmp_path / "rec.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    result = runner.invoke(
        app,
        [
            "clone",
            "review",
            "--name",
            "   ",
            "--audio",
            str(audio_file),
            "--transcript",
            "x",
            "--review-out",
            str(tmp_path / "review.json"),
        ],
    )

    assert result.exit_code == 2
    assert "voice name must not be empty" in result.output
    mock_convert.assert_not_called()


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_save_duplicate_exits_2(mock_convert, tmp_path):
    lib = tmp_path / "voices"
    audio_file = tmp_path / "rec.wav"
    review_file = tmp_path / "review.json"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    runner.invoke(
        app,
        [
            "clone",
            "review",
            "--audio",
            str(audio_file),
            "--transcript",
            "x",
            "--review-out",
            str(review_file),
            "--library",
            str(lib),
        ],
    )
    runner.invoke(
        app,
        ["clone", "save", "--review", str(review_file), "--id", "v1", "--name", "V1", "--library", str(lib)],
    )
    result = runner.invoke(
        app,
        ["clone", "save", "--review", str(review_file), "--id", "v1", "--name", "V1", "--library", str(lib)],
    )
    assert result.exit_code == 2
    assert mock_convert.call_count == 2


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_save_overwrite_replaces(mock_convert, tmp_path):
    lib = tmp_path / "voices"
    audio_file = tmp_path / "rec.wav"
    first_review = tmp_path / "first.json"
    second_review = tmp_path / "second.json"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    runner.invoke(
        app,
        ["clone", "review", "--audio", str(audio_file), "--transcript", "first", "--review-out", str(first_review)],
    )
    runner.invoke(
        app,
        ["clone", "save", "--review", str(first_review), "--id", "v1", "--name", "V1", "--library", str(lib)],
    )
    runner.invoke(
        app,
        ["clone", "review", "--audio", str(audio_file), "--transcript", "second", "--review-out", str(second_review)],
    )
    result = runner.invoke(
        app,
        [
            "clone",
            "save",
            "--review",
            str(second_review),
            "--id",
            "v1",
            "--name",
            "V1",
            "--overwrite",
            "--library",
            str(lib),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (lib / "v1" / "reference.txt").read_text(encoding="utf-8") == "second"
    assert mock_convert.call_count == 4


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_save_uses_required_name(mock_convert, tmp_path):
    lib = tmp_path / "voices"
    audio_file = tmp_path / "rec.wav"
    review_file = tmp_path / "review.json"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    runner.invoke(
        app,
        ["clone", "review", "--audio", str(audio_file), "--transcript", "x", "--review-out", str(review_file)],
    )
    result = runner.invoke(
        app,
        [
            "clone",
            "save",
            "--review",
            str(review_file),
            "--id",
            "deep_narrator",
            "--name",
            "Deep Narrator",
            "--library",
            str(lib),
        ],
    )
    assert result.exit_code == 0, result.output
    voice_json = (lib / "deep_narrator" / "voice.json").read_text(encoding="utf-8")
    assert '"name": "Deep Narrator"' in voice_json
    assert mock_convert.call_count == 2


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
@patch(
    "voices.cli_clone.prepare_clone_review",
    return_value=PreparedCloneReview(
        draft=TranscriptionDraft(
            transcript="Hello from local STT.",
            language="English",
            duration_seconds=4.0,
            segments=[],
        ),
        normalized_audio=MOCK_AUDIO,
        suggested_voice_id="played_voice",
    ),
)
def test_clone_review_runs_stt_when_transcript_omitted(mock_prepare_review, mock_convert, tmp_path):
    audio_file = tmp_path / "rec.opus"
    review_file = tmp_path / "review.json"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

    result = runner.invoke(
        app,
        ["--json", "clone", "review", "--audio", str(audio_file), "--review-out", str(review_file)],
    )

    assert result.exit_code == 0, result.output
    assert mock_prepare_review.call_count == 1
    payload = json.loads(result.output)
    assert payload["review"]["transcript"] == "Hello from local STT."
    assert review_file.with_suffix(".wav").exists()
    mock_convert.assert_not_called()


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
@patch(
    "voices.cli_review.prepare_clone_review",
    return_value=PreparedCloneReview(
        draft=TranscriptionDraft(
            transcript="My recorded line.",
            language="English",
            duration_seconds=14.0,
            segments=[],
        ),
        normalized_audio=MOCK_AUDIO,
        suggested_voice_id="my-voice",
    ),
)
@patch("voices.cli_review.play_wav")
@patch("voices.cli_review.record_guided_audio")
def test_record_guided_creates_voice(mock_record_guided, mock_play_wav, mock_prepare_review, mock_convert, tmp_path):
    lib = tmp_path / "voices"

    result = runner.invoke(
        app,
        ["record", "--language", "English", "--library", str(lib)],
        input="play\naccept\nMy Voice\n",
    )

    assert result.exit_code == 0, result.output
    assert mock_record_guided.call_count == 1
    assert mock_record_guided.call_args.args[1] == 30.0
    assert mock_prepare_review.call_count == 1
    mock_play_wav.assert_called_once()
    assert (lib / "my-voice" / "voice.json").exists()
    assert '"reference_text": "My recorded line."' in (lib / "my-voice" / "voice.json").read_text(encoding="utf-8")
    mock_convert.assert_called_once()


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
@patch(
    "voices.cli_review.prepare_clone_review",
    return_value=PreparedCloneReview(
        draft=TranscriptionDraft(
            transcript="My recorded line.",
            language="English",
            duration_seconds=14.0,
            segments=[],
        ),
        normalized_audio=MOCK_AUDIO,
        suggested_voice_id="ignored-suggestion",
    ),
)
@patch("voices.cli_review.record_guided_audio")
def test_record_rejects_blank_name_before_capture(mock_record_guided, mock_prepare_review, mock_convert, tmp_path):
    lib = tmp_path / "voices"

    result = runner.invoke(
        app,
        ["record", "--name", "   ", "--language", "English", "--library", str(lib)],
    )

    assert result.exit_code == 2
    assert "voice name must not be empty" in result.output
    mock_record_guided.assert_not_called()
    mock_prepare_review.assert_not_called()
    mock_convert.assert_not_called()


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
@patch(
    "voices.cli_review.prepare_clone_review",
    return_value=PreparedCloneReview(
        draft=TranscriptionDraft(
            transcript="Updated recorded line.",
            language="English",
            duration_seconds=14.0,
            segments=[],
        ),
        normalized_audio=MOCK_AUDIO,
        suggested_voice_id="my-voice-2",
    ),
)
@patch("voices.cli_review.record_guided_audio")
def test_record_overwrite_uses_name_derived_id(mock_record_guided, mock_prepare_review, mock_convert, tmp_path):
    lib = tmp_path / "voices"
    runner.invoke(
        app,
        ["record", "--name", "My Voice", "--language", "English", "--library", str(lib)],
        input="accept\n",
    )

    result = runner.invoke(
        app,
        ["record", "--name", "My Voice", "--overwrite", "--language", "English", "--library", str(lib)],
        input="accept\n",
    )

    assert result.exit_code == 0, result.output
    assert (lib / "my-voice" / "voice.json").exists()
    assert not (lib / "my-voice-2").exists()
    assert '"reference_text": "Updated recorded line."' in (lib / "my-voice" / "voice.json").read_text(encoding="utf-8")
    assert mock_record_guided.call_count == 2
    assert mock_prepare_review.call_count == 2
    assert mock_convert.call_count == 2


@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
@patch(
    "voices.cli_review.prepare_clone_review",
    side_effect=[
        InvalidInputError("Recorded take must be at least 3s before transcript review."),
        PreparedCloneReview(
            draft=TranscriptionDraft(
                transcript="Long enough take.",
                language="Italian",
                duration_seconds=4.5,
                segments=[],
            ),
            normalized_audio=MOCK_AUDIO,
            suggested_voice_id="free-voice",
        ),
    ],
)
@patch("voices.cli_review.free_recording")
def test_record_free_enforces_minimum_duration(
    mock_free_recording,
    mock_prepare_review,
    mock_convert,
    tmp_path,
):
    lib = tmp_path / "voices"

    result = runner.invoke(
        app,
        ["record", "--mode", "free", "--language", "Italian", "--name", "Free Voice", "--library", str(lib)],
        input="\n\naccept\n",
    )

    assert result.exit_code == 0, result.output
    assert mock_free_recording.call_count == 2
    assert mock_free_recording.return_value.__exit__.call_count == 2
    assert mock_prepare_review.call_count == 2
    assert (lib / "free-voice" / "voice.json").exists()
    assert '"language": "Italian"' in (lib / "free-voice" / "voice.json").read_text(encoding="utf-8")
    mock_convert.assert_called_once()
