"""CLI-to-sidecar identity tests with real publication and mocked inference only."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from helpers import MOCK_AUDIO, seed_voice
from mlx_audio.tts import utils as tts_utils
from pydantic import ValidationError
from typer.testing import CliRunner

from voices import config
from voices.adapter import mlx_qwen, mlx_runtime, model_snapshot
from voices.cli import app
from voices.domain.contracts import OutputDraft
from voices.runtime_identity import RuntimeIdentity
from voices.store.output_store import output_artifact_for_name
from voices.workflow import synthesize_voice

runner = CliRunner()


@pytest.fixture
def identity():
    return RuntimeIdentity(
        python="test-python",
        executable="/test/python",
        platform="test-platform",
        voices_version="test-version",
        source_sha256="b" * 64,
        packages={"mlx-audio": "test-version"},
    )


def render_args(library, out, revision):
    return [
        "--json",
        "render",
        "test_voice",
        "New line.",
        "--library",
        str(library),
        "--out-dir",
        str(out),
        "--model-revision",
        revision,
    ]


@pytest.mark.parametrize("revision", ["", "main", "latest", "a" * 39, "x" * 40])
def test_render_rejects_invalid_revision_before_loading_or_output(tmp_path, monkeypatch, revision):
    library, out = tmp_path / "library", tmp_path / "out"
    seed_voice(library)
    load = MagicMock(side_effect=AssertionError("must not load"))
    monkeypatch.setattr(mlx_qwen, "_get_runtime", load)
    result = runner.invoke(app, render_args(library, out, revision))
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "invalid_input"
    assert not out.exists()
    load.assert_not_called()


def test_exact_loaded_revision_and_pre_generation_identity_survive_configuration_changes(
    tmp_path, monkeypatch, identity
):
    library, out = tmp_path / "library", tmp_path / "out"
    seed_voice(library)
    selected_model = config.BASE_MODEL
    selected_revision = "c" * 40
    snapshot = tmp_path / "cache" / "snapshots" / selected_revision
    snapshot.mkdir(parents=True)
    monkeypatch.setattr(mlx_qwen, "_runtime_cache", {})
    monkeypatch.setattr(synthesize_voice, "get_runtime_identity", lambda: identity)

    def resolve(model_id, revision):
        assert mlx_runtime._runtime_lock.locked()
        assert (model_id, revision) == (selected_model, selected_revision)
        return snapshot

    runtime = MagicMock(spec=mlx_qwen.Qwen3TtsModel)
    runtime.sample_rate = 24000
    runtime._icl_cache = {}

    def generate(**_kwargs):
        # A post-inference read would now misattribute both model and source.
        monkeypatch.setattr(config, "BASE_MODEL", "changed/model")
        monkeypatch.setattr(config, "BASE_MODEL_REVISION", "d" * 40)
        monkeypatch.setattr(
            synthesize_voice, "get_runtime_identity", lambda: identity.model_copy(update={"source_sha256": "e" * 64})
        )
        yield MagicMock(audio=MOCK_AUDIO)

    runtime.generate.side_effect = generate
    load = MagicMock(return_value=runtime)
    monkeypatch.setattr(mlx_qwen, "resolve_model_snapshot", resolve)
    monkeypatch.setattr(tts_utils, "load_model", load)
    result = runner.invoke(app, render_args(library, out, selected_revision.upper()))
    assert result.exit_code == 0, result.output
    load.assert_called_once_with(snapshot)
    payload = json.loads(result.output)
    assert payload["artifact"]["base_model_id"] == selected_model
    assert payload["artifact"]["base_model_revision"] == selected_revision
    assert payload["artifact"]["runtime"] == identity.model_dump(mode="json")
    persisted = json.loads(Path(payload["paths"]["sidecar"]).read_text())
    assert persisted == payload["artifact"]
    assert Path(payload["paths"]["wav"]).is_file()


def test_missing_revision_is_json_failure_without_publishing_any_output(tmp_path, monkeypatch):
    library, out = tmp_path / "library", tmp_path / "out"
    seed_voice(library)
    monkeypatch.setattr(mlx_qwen, "_runtime_cache", {})
    download = MagicMock(side_effect=FileNotFoundError("requested revision is not cached"))
    monkeypatch.setattr(model_snapshot._hub, "snapshot_download", download)
    result = runner.invoke(app, render_args(library, out, "f" * 40))
    assert result.exit_code == 4, result.output
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "generation"
    assert "requested revision is not cached" in payload["error"]["message"]
    assert not out.exists()


def test_default_memory_projection_keeps_browser_shape_and_pins_revision(tmp_path, monkeypatch, identity):
    library = tmp_path / "library"
    seed_voice(library)
    synthesize = MagicMock(return_value=(MOCK_AUDIO, 24000))
    monkeypatch.setattr(synthesize_voice, "synthesize_reference_voice", synthesize)
    monkeypatch.setattr(synthesize_voice, "get_runtime_identity", lambda: identity)
    audio, sample_rate, voice = synthesize_voice.synthesize_to_memory(
        voice_id="test_voice",
        text="Browser preview.",
        language=None,
        library=library,
    )
    assert audio is MOCK_AUDIO
    assert sample_rate == 24000 and voice.id == "test_voice"
    assert synthesize.call_args.kwargs["model_revision"] == config.BASE_MODEL_REVISION
    assert synthesize.call_args.kwargs["model_id"] == config.BASE_MODEL


def test_historical_sidecar_reads_without_fabricating_revision_or_runtime(tmp_path):
    voice_out = tmp_path / "test_voice"
    voice_out.mkdir()
    wav = voice_out / "20260408T120000Z__old.wav"
    wav.write_bytes(b"historical audio fixture")
    sidecar = wav.with_suffix(".json")
    payload = {
        "schema_version": 2,
        "voice_id": "test_voice",
        "created_at": "2026-04-08T12:00:00Z",
        "language": "English",
        "base_model_id": config.BASE_MODEL,
        "text": "Old audio.",
        "output_audio": wav.name,
        "reference_voice_id": "test_voice",
        "reference_sha256": "a" * 64,
    }
    sidecar.write_text(json.dumps(payload))
    before = sidecar.read_bytes()
    artifact = output_artifact_for_name(tmp_path, "test_voice", wav.name)
    assert artifact.record.base_model_revision is None
    assert artifact.record.runtime is None
    assert artifact.record.reference_text_sha256 is None
    assert sidecar.read_bytes() == before


def test_new_output_draft_requires_revision_and_runtime():
    with pytest.raises(ValidationError) as error:
        OutputDraft.model_validate(
            {
                "voice_id": "test_voice",
                "created_at": "2026-04-08T12:00:00Z",
                "language": "English",
                "base_model_id": config.BASE_MODEL,
                "text": "New audio.",
                "reference_voice_id": "test_voice",
                "reference_sha256": "a" * 64,
            }
        )
    missing = {item["loc"] for item in error.value.errors() if item["type"] == "missing"}
    assert missing == {("base_model_revision",), ("runtime",), ("reference_text_sha256",)}
