import hashlib
import json
import shutil
import wave
from contextlib import contextmanager
from unittest.mock import MagicMock

import numpy as np
import pytest
from mlx_audio.stt.models.qwen3_forced_aligner import ForcedAlignItem, ForcedAlignResult, Model
from typer.testing import CliRunner

from voices import config
from voices.adapter import mlx_align
from voices.adapter.ffmpeg_audio import convert_to_reference_audio
from voices.cli import app
from voices.domain.alignment_contracts import AlignmentWord
from voices.domain.contracts import SUPPORTED_LANGUAGE_LABELS
from voices.domain.errors import GenerationError
from voices.runtime_identity import RuntimeIdentity
from voices.workflow import align_speech as workflow

REVISION = "b" * 40


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"source unchanged")
    text = tmp_path / "transcript.txt"
    text.write_text("  Hello world.\n")
    normalized = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(workflow, "convert_to_reference_audio", lambda *a, **k: normalized)
    monkeypatch.setattr(workflow, "find_spec", lambda name: object())
    monkeypatch.setattr(
        workflow,
        "get_runtime_identity",
        lambda: RuntimeIdentity(
            python="test",
            executable="test",
            platform="test",
            voices_version="test",
            source_sha256="a" * 64,
            packages={},
        ),
    )
    aligner = MagicMock(
        return_value=[AlignmentWord(text="Hello", start=0, end=0), AlignmentWord(text="world", start=0, end=1)]
    )
    monkeypatch.setattr(workflow, "align_audio", aligner)
    return audio, text, normalized, aligner


def test_cli_alignment_json_preserves_exact_input_and_zero_width(inputs):
    audio, text, normalized, aligner = inputs
    before = (audio.read_bytes(), text.read_bytes())
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "align",
            "--audio",
            str(audio),
            "--text-file",
            str(text),
            "--language",
            "english",
            "--model-revision",
            REVISION,
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert result.stderr == ""
    assert payload["model_id"] == config.ALIGNER_MODEL
    assert payload["model_revision"] == REVISION
    assert payload["language"] == "English"
    assert payload["text"] == "  Hello world.\n"
    assert payload["audio"]["path"] == str(audio.resolve())
    assert payload["audio"]["sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert payload["audio"]["normalized_sha256"] == hashlib.sha256(normalized.tobytes()).hexdigest()
    assert payload["audio"]["normalized_dtype"] == "<f4"
    assert payload["audio"]["sample_rate"] == 16000
    assert payload["audio"]["duration_seconds"] == 1
    assert payload["spoken_content_verified"] is False
    assert payload["timing_diagnostics"] is None
    assert payload["words"][0] == {"text": "Hello", "start": 0, "end": 0}
    assert payload["runtime"]["source_sha256"] == "a" * 64
    assert (audio.read_bytes(), text.read_bytes()) == before
    assert aligner.call_args.args[1:] == ("  Hello world.\n", "English", REVISION)
    assert aligner.call_args.kwargs == {"model_id": config.ALIGNER_MODEL}


def test_provenance_retains_model_selection_when_config_changes_during_generation(inputs, monkeypatch):
    audio, text, _, aligner = inputs
    original_model = config.ALIGNER_MODEL
    original_revision = config.ALIGNER_MODEL_REVISION
    expected_words = aligner.return_value

    def generate(*args, model_id):
        assert model_id == original_model
        assert args[3] == original_revision
        monkeypatch.setattr(config, "ALIGNER_MODEL", "different/model")
        monkeypatch.setattr(config, "ALIGNER_MODEL_REVISION", "d" * 40)
        return expected_words

    aligner.side_effect = generate
    result = workflow.align_speech(audio=audio, text_file=text, language="English")
    assert result.model_id == original_model
    assert result.model_revision == original_revision


@pytest.mark.parametrize("kind", ["audio", "text", "empty", "utf8", "language", "revision"])
def test_bad_inputs_fail_before_alignment(inputs, kind):
    audio, text, _, aligner = inputs
    language, revision = "English", REVISION
    if kind == "audio":
        audio.unlink()
    elif kind == "text":
        text.unlink()
    elif kind == "empty":
        text.write_text(" \n")
    elif kind == "utf8":
        text.write_bytes(b"\xff")
    elif kind == "language":
        language = "Martian"
    else:
        revision = "main"
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "align",
            "--audio",
            str(audio),
            "--text-file",
            str(text),
            "--language",
            language,
            "--model-revision",
            revision,
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid_input"
    aligner.assert_not_called()


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGE_LABELS)
def test_supported_labels_normalized_without_model_load(inputs, language):
    audio, text, _, aligner = inputs
    result = workflow.align_speech(audio=audio, text_file=text, language=f" {language.lower()} ")
    assert result.language == language
    assert aligner.call_args.args[3] == config.ALIGNER_MODEL_REVISION


@pytest.mark.parametrize("language,package", [("Japanese", "nagisa"), ("Korean", "soynlp")])
def test_optional_tokenizer_missing_before_alignment(inputs, monkeypatch, language, package):
    audio, text, _, aligner = inputs
    monkeypatch.setattr(workflow, "find_spec", lambda name: None)
    result = CliRunner().invoke(
        app, ["--json", "align", "--audio", str(audio), "--text-file", str(text), "--language", language]
    )
    assert result.exit_code == 5
    assert package in json.loads(result.stdout)["error"]["message"]
    aligner.assert_not_called()


@pytest.mark.parametrize(
    "words",
    [
        [],
        [AlignmentWord(text="hello", start=0, end=1.002)],
        [AlignmentWord(text="one", start=0, end=0.7), AlignmentWord(text="two", start=0.6, end=0.8)],
    ],
)
def test_invalid_timeline_becomes_product_error(inputs, words):
    audio, text, _, aligner = inputs
    aligner.return_value = words
    with pytest.raises(GenerationError, match="invalid timeline"):
        workflow.align_speech(audio=audio, text_file=text, language="English")


def test_one_millisecond_rounding_tolerance(inputs):
    audio, text, _, aligner = inputs
    aligner.return_value = [AlignmentWord(text="Hello", start=0, end=1.001)]
    assert workflow.align_speech(audio=audio, text_file=text, language="English").words[0].end == 1.001


def test_source_change_during_normalization_rejected_before_model(inputs, monkeypatch):
    audio, text, normalized, aligner = inputs

    def changing_source(*args, **kwargs):
        audio.write_bytes(b"different source")
        return normalized

    monkeypatch.setattr(workflow, "convert_to_reference_audio", changing_source)
    result = CliRunner().invoke(
        app, ["--json", "align", "--audio", str(audio), "--text-file", str(text), "--language", "English"]
    )
    assert result.exit_code == 2
    assert "changed during normalization" in json.loads(result.stdout)["error"]["message"]
    aligner.assert_not_called()


@pytest.mark.parametrize(
    "items",
    [
        [],
        [ForcedAlignItem("bad", float("nan"), 1)],
        [ForcedAlignItem("bad", 1, 0)],
        [ForcedAlignItem("bad", -1, 0)],
        [ForcedAlignItem("", 0, 1)],
    ],
)
def test_invalid_upstream_words_rejected(monkeypatch, items):
    runtime = MagicMock()
    runtime.generate.return_value = ForcedAlignResult(items)
    monkeypatch.setattr(mlx_align, "_get_runtime", lambda *args: runtime)
    with pytest.raises(GenerationError):
        mlx_align.align_audio(np.zeros(16000), "Hello", "English", REVISION, model_id=config.ALIGNER_MODEL)


def test_unexpected_upstream_type_rejected(monkeypatch):
    runtime = MagicMock()
    runtime.generate.return_value = object()
    monkeypatch.setattr(mlx_align, "_get_runtime", lambda *args: runtime)
    with pytest.raises(GenerationError, match="unexpected result"):
        mlx_align.align_audio(np.zeros(16000), "Hello", "English", REVISION, model_id=config.ALIGNER_MODEL)


def test_malformed_upstream_item_rejected(monkeypatch):
    runtime = MagicMock()
    runtime.generate.return_value = ForcedAlignResult([object()])
    monkeypatch.setattr(mlx_align, "_get_runtime", lambda *args: runtime)
    with pytest.raises(GenerationError, match="unexpected word item"):
        mlx_align.align_audio(np.zeros(16000), "Hello", "English", REVISION, model_id=config.ALIGNER_MODEL)


@pytest.mark.parametrize(
    "error,expected",
    [(RuntimeError("metal failed"), GenerationError), (ImportError("tokenizer"), workflow.MissingDependencyError)],
)
def test_upstream_errors_normalized(monkeypatch, error, expected):
    runtime = MagicMock()
    runtime.generate.side_effect = error
    monkeypatch.setattr(mlx_align, "_get_runtime", lambda *args: runtime)
    with pytest.raises(expected):
        mlx_align.align_audio(np.zeros(16000), "Hello", "English", REVISION, model_id=config.ALIGNER_MODEL)


@pytest.mark.parametrize("normalized", [np.array([]), np.array([float("inf")]), np.zeros((3, 2))])
def test_invalid_normalized_audio_never_loads_aligner(inputs, monkeypatch, normalized):
    audio, text, _, aligner = inputs
    monkeypatch.setattr(workflow, "convert_to_reference_audio", lambda *args, **kwargs: normalized)
    with pytest.raises(workflow.AudioConversionError):
        workflow.align_speech(audio=audio, text_file=text, language="English")
    aligner.assert_not_called()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg not installed")
def test_real_normalization_preserves_source_and_hashes_model_array(inputs, monkeypatch):
    audio, text, _, aligner = inputs
    with wave.open(str(audio), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(np.zeros((24000, 2), dtype="<i2").tobytes())
    original = audio.read_bytes()
    monkeypatch.setattr(workflow, "convert_to_reference_audio", convert_to_reference_audio)
    result = workflow.align_speech(audio=audio, text_file=text, language="English")
    actual = aligner.call_args.args[0]
    assert actual.shape == (16000,)
    assert actual.dtype.str == "<f4"
    assert result.audio.normalized_sha256 == hashlib.sha256(actual.tobytes()).hexdigest()
    assert result.audio.sha256 == hashlib.sha256(original).hexdigest()
    assert audio.read_bytes() == original


def test_snapshot_load_generation_and_cache_clear_serialize(monkeypatch, tmp_path, capsys):
    import mlx_audio.stt.utils

    events = []
    locked = False
    snapshot = tmp_path / "snapshots" / REVISION
    runtime = MagicMock(spec=Model)

    @contextmanager
    def guard():
        nonlocal locked
        assert not locked
        locked = True
        events.append("enter")
        yield
        events.append("exit")
        locked = False

    def resolve(model_id, revision):
        assert locked
        assert model_id == config.ALIGNER_MODEL
        events.append(("resolve", revision))
        return snapshot

    def load(path, *, strict, model_type):
        assert locked and strict and path == snapshot
        assert model_type == "qwen3_forced_aligner"
        print("upstream loader noise")
        return runtime

    def generate(**kwargs):
        assert locked
        print("upstream generation noise")
        events.append("generate and upstream cache clear")
        return ForcedAlignResult([ForcedAlignItem("Hello", 0, 0.5)])

    class GuardedCache(dict):
        def clear(self):
            assert locked
            events.append("clear")
            super().clear()

    runtime.generate.side_effect = generate
    monkeypatch.setattr(mlx_align, "serialized_mlx_runtime", guard)
    monkeypatch.setattr(mlx_align, "resolve_model_snapshot", resolve)
    monkeypatch.setattr(mlx_audio.stt.utils, "load", load)
    monkeypatch.setattr(mlx_align, "_runtime_cache", GuardedCache())
    for revision in [REVISION, REVISION, "c" * 40]:
        assert (
            mlx_align.align_audio(np.zeros(16000), "Hello", "English", revision, model_id=config.ALIGNER_MODEL)[0].end
            == 0.5
        )
    mlx_align.clear_runtime_cache()
    assert events.count(("resolve", REVISION)) == 1
    assert events.count(("resolve", "c" * 40)) == 1
    assert events[-3:] == ["enter", "clear", "exit"]
    assert capsys.readouterr().out == ""
