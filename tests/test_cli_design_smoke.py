import json
from unittest.mock import patch

from helpers import MOCK_AUDIO
from typer.testing import CliRunner

from voices.cli import app

runner = CliRunner()


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_creates_voice(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    result = runner.invoke(
        app,
        [
            "design",
            "--id",
            "v1",
            "--instruct",
            "Low narrator",
            "--text",
            "Hello world.",
            "--library",
            str(lib),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (lib / "v1" / "reference.wav").exists()
    assert (lib / "v1" / "reference.txt").exists()
    assert (lib / "v1" / "voice.json").exists()
    mock_design_audio.assert_called_once_with(
        text="Hello world.",
        instruct="Low narrator",
        language="English",
    )


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_duplicate_exits_2(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    runner.invoke(
        app,
        ["design", "--id", "v1", "--instruct", "x", "--text", "y", "--library", str(lib)],
    )
    result = runner.invoke(
        app,
        ["design", "--id", "v1", "--instruct", "x", "--text", "y", "--library", str(lib)],
    )
    assert result.exit_code == 2
    assert mock_design_audio.call_count == 1


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_rejects_invalid_voice_id_before_generation(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    result = runner.invoke(
        app,
        [
            "design",
            "--id",
            ".",
            "--instruct",
            "Low narrator",
            "--text",
            "Hello world.",
            "--library",
            str(lib),
        ],
    )
    assert result.exit_code == 2
    assert "voice id must match" in result.output
    mock_design_audio.assert_not_called()


def test_design_rejects_unsupported_language(tmp_path):
    result = runner.invoke(
        app,
        [
            "design",
            "--id",
            "v1",
            "--instruct",
            "Low narrator",
            "--text",
            "Hello world.",
            "--language",
            "Auto",
            "--library",
            str(tmp_path / "voices"),
        ],
    )
    assert result.exit_code == 2
    assert "language must be one of" in result.output


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_rejects_blank_prompt_before_generation(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    result = runner.invoke(
        app,
        [
            "design",
            "--id",
            "v1",
            "--instruct",
            "   ",
            "--text",
            "Hello world.",
            "--library",
            str(lib),
        ],
    )

    assert result.exit_code == 2
    mock_design_audio.assert_not_called()


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_rejects_blank_name_before_generation(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    result = runner.invoke(
        app,
        [
            "design",
            "--id",
            "v1",
            "--name",
            "   ",
            "--instruct",
            "Low narrator",
            "--text",
            "Hello world.",
            "--library",
            str(lib),
        ],
    )

    assert result.exit_code == 2
    assert "voice name must not be empty" in result.output
    mock_design_audio.assert_not_called()


@patch("voices.workflow.design_voice.design_reference_audio")
def test_design_json_dry_run_does_not_generate(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    result = runner.invoke(
        app,
        [
            "--json",
            "design",
            "--id",
            "v1",
            "--instruct",
            "Low narrator",
            "--text",
            "Hello world.",
            "--library",
            str(lib),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["voice"]["id"] == "v1"
    assert not (lib / "v1").exists()
    mock_design_audio.assert_not_called()


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_batch_jsonl(mock_design_audio, tmp_path):
    lib = tmp_path / "voices"
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text('{"id":"a","instruct":"x"}\n{"id":"b","instruct":"y"}\n', encoding="utf-8")
    result = runner.invoke(
        app,
        ["design-batch", str(prompts), "--text", "Hello.", "--library", str(lib)],
    )
    assert result.exit_code == 0, result.output
    assert (lib / "a" / "voice.json").exists()
    assert (lib / "b" / "voice.json").exists()
    assert mock_design_audio.call_count == 2


@patch("voices.workflow.design_voice.design_reference_audio")
def test_design_batch_continues_on_error(mock_design_audio, tmp_path):
    from voices.domain.errors import GenerationError

    mock_design_audio.side_effect = [
        (MOCK_AUDIO, 24000),
        GenerationError("boom"),
        (MOCK_AUDIO, 24000),
    ]
    lib = tmp_path / "voices"
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(
        '{"id":"a","instruct":"x"}\n{"id":"b","instruct":"y"}\n{"id":"c","instruct":"z"}\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["design-batch", str(prompts), "--text", "Hello.", "--library", str(lib)],
    )
    assert result.exit_code == 4
    assert (lib / "a" / "voice.json").exists()
    assert not (lib / "b").exists()
    assert (lib / "c" / "voice.json").exists()
    assert "boom" in result.output


def test_design_batch_invalid_prompt_exits_2(tmp_path):
    prompt_file = tmp_path / "prompts.jsonl"
    prompt_file.write_text('{"id":"v1"}\n', encoding="utf-8")

    result = runner.invoke(app, ["design-batch", str(prompt_file), "--text", "Hello."])

    assert result.exit_code == 2
    assert "invalid prompt entry" in result.output


def test_design_batch_json_dry_run(tmp_path):
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text('{"id":"a","instruct":"x"}\n{"id":"b","instruct":"y"}\n', encoding="utf-8")

    result = runner.invoke(app, ["--json", "design-batch", str(prompts), "--text", "Hello.", "--dry-run"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] == 2
    assert payload["items"][0]["id"] == "a"
