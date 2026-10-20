import json
import os
from pathlib import Path
from unittest.mock import patch

from helpers import MOCK_AUDIO, make_design_draft, make_design_record, seed_voice
from typer.testing import CliRunner

from voices import config
from voices.cli import app
from voices.cli_diagnostics import _readiness_value
from voices.cli_support import select_voice_id
from voices.store.library_store import save_voice_record

runner = CliRunner()


def test_list_shows_table(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib, "my_voice")
    result = runner.invoke(app, ["list", "--library", str(lib)])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "lang" in result.output
    assert "source" in result.output
    assert "desc" in result.output
    assert "my_voice" in result.output
    assert "English" in result.output
    assert "design" in result.output
    assert "Low narrator" in result.output
    assert "Name" not in result.output
    assert "Created" not in result.output


def test_list_shows_full_description(tmp_path):
    lib = tmp_path / "voices"
    description = (
        "Calm documentary narrator with measured pacing, clean diction, and quiet authority that keeps "
        "the rhythm steady through long passages without sounding detached. SentinelTail"
    )
    save_voice_record(
        lib,
        make_design_draft("long_voice", instruct=description),
        MOCK_AUDIO,
        24000,
    )

    result = runner.invoke(app, ["list", "--library", str(lib)])

    assert result.exit_code == 0
    assert "SentinelTail" in result.output


def test_list_empty(tmp_path):
    result = runner.invoke(app, ["list", "--library", str(tmp_path / "empty")])
    output = " ".join(result.output.split())
    assert result.exit_code == 0
    assert "No voices found" in result.output
    assert "voices design" in output
    assert "voices clone review" in output
    assert "voices clone save" in output
    assert "voices record" in output


@patch("voices.cli_diagnostics.shutil.which", return_value="/opt/homebrew/bin/ffmpeg")
def test_doctor_reports_local_readiness(mock_which, tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib, "doctor_voice")

    result = runner.invoke(app, ["doctor", "--library", str(lib)])

    assert result.exit_code == 0, result.output
    assert "Voices Doctor" in result.output
    assert "library" in result.output
    assert "(ready)" in result.output
    assert "voices" in result.output
    assert "1" in result.output
    assert "studio bundle" in result.output
    assert "/opt/homebrew/bin/ffmpeg" in result.output
    mock_which.assert_called_once_with("ffmpeg")


@patch("voices.cli_diagnostics.shutil.which", return_value="/opt/homebrew/bin/ffmpeg")
def test_doctor_uses_expanded_library_root(mock_which, monkeypatch, tmp_path):
    home = tmp_path / "home"
    lib = home / "voices"
    seed_voice(lib, "doctor_voice")
    monkeypatch.setenv("HOME", str(home))

    result = runner.invoke(app, ["doctor"], env={"VOICES_LIBRARY": "~/voices"})

    assert result.exit_code == 0, result.output
    assert "│ voices        │ 1" in result.output
    mock_which.assert_called_once_with("ffmpeg")


@patch("voices.cli_diagnostics.shutil.which", return_value="/opt/homebrew/bin/ffmpeg")
def test_doctor_json_reports_no_auth_and_models(mock_which, tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib, "doctor_voice")

    result = runner.invoke(app, ["--json", "doctor", "--library", str(lib)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["auth_required"] is False
    assert payload["library"]["source"] == "cli"
    assert payload["library"]["voice_count"] == 1
    assert payload["ffmpeg"]["path"] == "/opt/homebrew/bin/ffmpeg"
    assert payload["models"]["base"].startswith("mlx-community/Qwen3-TTS")
    assert payload["models"]["aligner"] == "mlx-community/Qwen3-ForcedAligner-0.6B-bf16"
    assert set(payload["model_revisions"]) == set(payload["models"])
    assert all(len(revision) == 40 for revision in payload["model_revisions"].values())
    assert Path(payload["model_cache"]).is_absolute()
    runtime = payload["runtime"]
    assert Path(runtime["executable"]).is_absolute()
    assert len(runtime["source_sha256"]) == 64
    assert runtime["packages"]["mlx-audio"]
    assert runtime["package_scope"] == "selected-runtime-dependencies"
    mock_which.assert_called_once_with("ffmpeg")


def test_readiness_value_checks_expanded_path(monkeypatch, tmp_path):
    home = tmp_path / "home"
    library = home / "voices"
    library.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    assert _readiness_value(Path("~/voices")).endswith("(ready)")


def test_readiness_value_checks_required_file(tmp_path):
    web_dist = tmp_path / "dist"
    web_dist.mkdir()

    assert _readiness_value(web_dist, required_file=web_dist / "index.html").endswith("(missing)")

    (web_dist / "index.html").write_text("<!doctype html>", encoding="utf-8")

    assert _readiness_value(web_dist, required_file=web_dist / "index.html").endswith("(ready)")


def test_say_empty_library_guidance_mentions_all_creation_paths(tmp_path):
    result = runner.invoke(app, ["say", "Hello.", "--library", str(tmp_path / "empty")])
    output = " ".join(result.output.split())
    assert result.exit_code == 3
    assert "voices design" in output
    assert "voices clone review" in output
    assert "voices clone save" in output
    assert "voices record" in output


def test_say_default_voice_uses_latest_same_timestamp_save(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(
        lib,
        make_design_draft("zulu", created_at="2026-04-08T12:00:00Z"),
        MOCK_AUDIO,
        24000,
    )
    save_voice_record(
        lib,
        make_design_draft("alpha", created_at="2026-04-08T12:00:00Z"),
        MOCK_AUDIO,
        24000,
    )
    os.utime(lib / "zulu" / "voice.json", ns=(100, 100))
    os.utime(lib / "alpha" / "voice.json", ns=(200, 200))

    assert select_voice_id(lib, None) == "alpha"


def test_show_displays_metadata(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(app, ["show", "test_voice", "--library", str(lib)])
    assert result.exit_code == 0
    assert "test_voice" in result.output
    assert "source_kind" in result.output
    assert "Low narrator" in result.output


def test_show_rejects_invalid_voice_id(tmp_path):
    result = runner.invoke(app, ["show", "Bad-ID", "--library", str(tmp_path / "voices")])
    assert result.exit_code == 2
    assert "voice id must match" in result.output


def test_show_json_rejects_invalid_voice_id_with_error_payload(tmp_path):
    result = runner.invoke(app, ["--json", "show", "Bad-ID", "--library", str(tmp_path / "voices")])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "invalid_input"
    assert "voice id must match" in payload["error"]["message"]


def test_list_json_filters_and_limits(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib, "noir_voice")
    save_voice_record(lib, make_design_draft("bright_voice", language="Italian"), MOCK_AUDIO, 24000)

    result = runner.invoke(
        app,
        [
            "--json",
            "list",
            "--language",
            "English",
            "--source",
            "design",
            "--query",
            "noir",
            "--limit",
            "1",
            "--library",
            str(lib),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert payload["limit"] == 1
    assert payload["items"][0]["id"] == "noir_voice"


def test_resolve_json_returns_stable_id(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib, "test_voice")

    result = runner.invoke(app, ["--json", "resolve", "Test Voice", "--library", str(lib)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["voice_id"] == "test_voice"
    assert payload["match"] == "name"


@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_render_creates_output(mock_synthesize, tmp_path):
    lib = tmp_path / "voices"
    out_dir = tmp_path / "outputs"
    seed_voice(lib)
    result = runner.invoke(
        app,
        ["render", "test_voice", "New line.", "--library", str(lib), "--out-dir", str(out_dir)],
    )
    assert result.exit_code == 0, result.output
    wavs = list((out_dir / "test_voice").glob("*.wav"))
    sidecars = list((out_dir / "test_voice").glob("*.json"))
    assert len(wavs) == 1
    assert len(sidecars) == 1
    payload = sidecars[0].read_text(encoding="utf-8")
    assert '"reference_voice_id": "test_voice"' in payload
    assert '"source_reference_audio"' not in payload
    mock_synthesize.assert_called_once()
    call_kwargs = mock_synthesize.call_args.kwargs
    assert call_kwargs["text"] == "New line."
    assert call_kwargs["reference_text"] == "Hello world."
    assert call_kwargs["language"] == "English"
    assert call_kwargs["reference_audio"] == (tmp_path / "voices" / "test_voice" / "reference.wav").read_bytes()


@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_render_json_and_outputs_inspection(mock_synthesize, tmp_path):
    lib = tmp_path / "voices"
    out_dir = tmp_path / "outputs"
    seed_voice(lib)

    render_result = runner.invoke(
        app,
        ["--json", "render", "test_voice", "New line.", "--library", str(lib), "--out-dir", str(out_dir)],
    )

    assert render_result.exit_code == 0, render_result.output
    render_payload = json.loads(render_result.output)
    wav_path = Path(render_payload["paths"]["wav"])
    assert render_payload["artifact"]["voice_id"] == "test_voice"

    list_result = runner.invoke(
        app,
        ["--json", "outputs", "list", "--voice", "test_voice", "--out-dir", str(out_dir), "--limit", "1"],
    )
    show_result = runner.invoke(
        app,
        ["--json", "outputs", "show", "test_voice", str(wav_path), "--out-dir", str(out_dir)],
    )

    assert list_result.exit_code == 0, list_result.output
    assert json.loads(list_result.output)["items"][0]["output_audio"] == wav_path.name
    assert show_result.exit_code == 0, show_result.output
    assert json.loads(show_result.output)["artifact"]["output_audio"] == wav_path.name
    mock_synthesize.assert_called_once()


def test_outputs_list_rejects_invalid_sidecar_contract(tmp_path):
    out_dir = tmp_path / "outputs"
    target_dir = out_dir / "test_voice"
    target_dir.mkdir(parents=True)
    wav_name = "20260408T120000Z__hello-world.wav"
    (target_dir / wav_name).write_bytes(b"RIFF")
    payload = {
        "schema_version": 2,
        "voice_id": "test_voice",
        "created_at": "2026-04-08T12:00:00Z",
        "language": "English",
        "base_model_id": config.BASE_MODEL,
        "text": "Hello world.",
        "output_audio": wav_name,
        "reference_voice_id": "test_voice",
        "reference_sha256": "a" * 64,
    }
    (target_dir / "not-canonical.json").write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["--json", "outputs", "list", "--voice", "test_voice", "--out-dir", str(out_dir)])

    assert result.exit_code == 5
    assert json.loads(result.output)["error"]["code"] == "invalid_output_entry"
    assert "invalid entries" in json.loads(result.output)["error"]["message"]


def test_render_missing_voice_exits_3(tmp_path):
    result = runner.invoke(app, ["render", "nonexistent", "Hello.", "--library", str(tmp_path)])
    assert result.exit_code == 3


def test_render_requires_text_or_file(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(app, ["render", "test_voice", "--library", str(lib)])
    assert result.exit_code == 2


def test_render_rejects_invalid_voice_id(tmp_path):
    result = runner.invoke(app, ["render", "foo/bar", "Hello.", "--library", str(tmp_path / "voices")])
    assert result.exit_code == 2
    assert "voice id must match" in result.output


def test_render_rejects_removed_overwrite_option(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(
        app,
        ["render", "test_voice", "Hello.", "--overwrite", "--library", str(lib)],
    )
    assert result.exit_code == 2
    assert "No such option" in result.output


@patch("voices.cli_speech.play_wav")
@patch("voices.cli_speech.write_wav")
@patch("voices.cli_speech.synthesize_to_memory", return_value=(MOCK_AUDIO, 24000, make_design_record()))
def test_say_uses_ephemeral_memory_path(mock_synthesize, mock_write_wav, mock_play_wav, tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(
        app,
        ["say", "We proceed at dawn.", "--voice", "test_voice", "--library", str(lib)],
    )
    assert result.exit_code == 0, result.output
    mock_synthesize.assert_called_once()
    mock_write_wav.assert_called_once()
    mock_play_wav.assert_called_once()
    assert not (tmp_path / "outputs").exists()


def test_say_rejects_invalid_requested_voice_id(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(app, ["say", "Hello.", "--voice", "Bad-ID", "--library", str(lib)])
    assert result.exit_code == 2
    assert "voice id must match" in result.output


@patch("voices.cli_speech.synthesize_to_memory", return_value=(MOCK_AUDIO, 24000, make_design_record()))
def test_say_rejects_blank_text_before_synthesis(mock_synthesize, tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(app, ["say", "   ", "--voice", "test_voice", "--library", str(lib)])
    assert result.exit_code == 2
    mock_synthesize.assert_not_called()


def test_delete_removes_directory(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)
    result = runner.invoke(app, ["delete", "test_voice", "--yes", "--library", str(lib)])
    assert result.exit_code == 0
    assert not (lib / "test_voice").exists()


def test_delete_json_requires_yes_or_dry_run(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)

    result = runner.invoke(app, ["--json", "delete", "test_voice", "--library", str(lib)])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "invalid_input"
    assert (lib / "test_voice").exists()


def test_delete_dry_run_keeps_directory(tmp_path):
    lib = tmp_path / "voices"
    seed_voice(lib)

    result = runner.invoke(app, ["--json", "delete", "test_voice", "--dry-run", "--library", str(lib)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["deleted"] is False
    assert (lib / "test_voice").exists()


def test_delete_rejects_invalid_voice_id(tmp_path):
    result = runner.invoke(app, ["delete", "foo/bar", "--yes", "--library", str(tmp_path / "voices")])
    assert result.exit_code == 2
    assert "voice id must match" in result.output
