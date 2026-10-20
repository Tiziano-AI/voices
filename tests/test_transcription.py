"""Audio-only CLI transcription without downloads, devices or library changes."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import wave
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from mlx_audio.stt.models.base import STTOutput
from mlx_audio.stt.models.qwen3_asr.qwen3_asr import Model
from typer.testing import CliRunner

from voices import config
from voices.adapter import mlx_stt
from voices.cli import app
from voices.domain.create_contracts import TranscriptionDraft
from voices.domain.errors import AudioConversionError, GenerationError, InvalidInputError
from voices.runtime_identity import RuntimeIdentity
from voices.workflow import transcribe_speech as workflow

REVISION = "b" * 40


def _wav(path):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(np.zeros((24000, 2), dtype="<i2").tobytes())
    return path


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    audio = _wav(tmp_path / "speech.wav")
    normalized = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(workflow, "convert_to_reference_audio", lambda *a, **k: normalized)
    runtime = RuntimeIdentity(
        python="test", executable="test", platform="test", voices_version="test", source_sha256="a" * 64, packages={}
    )
    monkeypatch.setattr(workflow, "get_runtime_identity", lambda: runtime)
    transcriber = MagicMock(
        return_value=TranscriptionDraft(transcript="Hello world.", language="English", duration_seconds=1, segments=[])
    )
    monkeypatch.setattr(workflow, "transcribe_audio", transcriber)
    return audio, normalized, transcriber


@pytest.mark.parametrize("language", ["English", "Italian"])
def test_json_transcription_has_audio_model_and_runtime_identity(inputs, language):
    audio, normalized, transcriber = inputs
    before = audio.read_bytes()
    result = CliRunner().invoke(
        app,
        ["--json", "transcribe", "--audio", str(audio), "--language", language.lower(), "--model-revision", REVISION],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert set(payload) == {"transcript", "language", "model_id", "model_revision", "runtime", "audio"}
    assert payload["transcript"] == "Hello world."
    assert payload["language"] == language
    assert payload["model_id"] == config.STT_MODEL
    assert payload["model_revision"] == REVISION
    assert payload["runtime"]["source_sha256"] == "a" * 64
    assert payload["audio"] == {
        "path": str(audio.resolve()),
        "sha256": hashlib.sha256(before).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized.tobytes()).hexdigest(),
        "normalized_dtype": "<f4",
        "channels": 1,
        "sample_rate": 16000,
        "duration_seconds": 1,
        "waveform_basis": "ffmpeg-normalized-mono-pcm16-to-float32",
    }
    assert result.stderr == ""
    assert audio.read_bytes() == before
    assert transcriber.call_args.args[1] == language
    assert transcriber.call_args.kwargs == {"model_revision": REVISION, "model_id": config.STT_MODEL}


def test_model_selection_and_runtime_are_observed_before_inference(inputs, monkeypatch):
    audio, _, transcriber = inputs
    original_model = config.STT_MODEL
    expected = transcriber.return_value

    def infer(*args, model_id, model_revision):
        assert model_id == original_model
        assert model_revision == REVISION
        monkeypatch.setattr(config, "STT_MODEL", "other/model")
        monkeypatch.setattr(config, "STT_MODEL_REVISION", "c" * 40)
        monkeypatch.setattr(workflow, "get_runtime_identity", lambda: pytest.fail("runtime observed after inference"))
        return expected

    transcriber.side_effect = infer
    result = workflow.transcribe_speech(audio=audio, language="English", model_revision=REVISION.upper())
    assert result.model_id == original_model
    assert result.model_revision == REVISION


@pytest.mark.parametrize("kind", ["missing", "directory", "not_wav", "language", "revision"])
def test_invalid_input_never_enters_inference(inputs, kind):
    audio, _, transcriber = inputs
    language, revision = "English", REVISION
    if kind == "missing":
        audio.unlink()
    elif kind == "directory":
        audio = audio.parent
    elif kind == "not_wav":
        audio.write_bytes(b"not a WAV despite the extension")
    elif kind == "language":
        language = "en"
    else:
        revision = "main"
    result = CliRunner().invoke(
        app,
        ["--json", "transcribe", "--audio", str(audio), "--language", language, "--model-revision", revision],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid_input"
    transcriber.assert_not_called()


@pytest.mark.parametrize("normalized", [np.array([]), np.array([float("nan")]), np.zeros((3, 2))])
def test_invalid_normalized_audio_never_enters_inference(inputs, monkeypatch, normalized):
    audio, _, transcriber = inputs
    monkeypatch.setattr(workflow, "convert_to_reference_audio", lambda *a, **k: normalized)
    with pytest.raises(AudioConversionError):
        workflow.transcribe_speech(audio=audio, language="English", model_revision=REVISION)
    transcriber.assert_not_called()


def test_changed_source_never_enters_inference(inputs, monkeypatch):
    audio, normalized, transcriber = inputs

    def convert(*args, **kwargs):
        audio.write_bytes(audio.read_bytes() + b"changed")
        return normalized

    monkeypatch.setattr(workflow, "convert_to_reference_audio", convert)
    with pytest.raises(InvalidInputError, match="changed during normalization"):
        workflow.transcribe_speech(audio=audio, language="English", model_revision=REVISION)
    transcriber.assert_not_called()


def test_human_transcription_has_no_rich_markup_interpretation(inputs):
    audio, _, transcriber = inputs
    transcriber.return_value = TranscriptionDraft(
        transcript="[red]Hello[/red]", language="English", duration_seconds=1, segments=[]
    )
    result = CliRunner().invoke(
        app, ["transcribe", "--audio", str(audio), "--language", "English", "--model-revision", REVISION]
    )
    assert result.exit_code == 0
    assert "[red]Hello[/red]" in result.stdout


def test_snapshot_selection_generation_and_cleanup_use_existing_lock(monkeypatch, tmp_path, capsys):
    import mlx_audio.stt.utils

    events = []
    locked = False
    model_id = config.STT_MODEL
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

    def resolve(selected, revision):
        assert locked and selected == model_id
        events.append(("resolve", revision))
        return tmp_path / "snapshots" / revision

    def load(path):
        assert locked and path.parent.name == "snapshots"
        print("loader noise")
        return runtime

    def generate(*args, **kwargs):
        assert locked
        print("generation noise")
        return STTOutput(text="Ciao mondo.", segments=[], language="Italian")

    class GuardedCache(dict):
        def clear(self):
            assert locked
            events.append("clear")
            super().clear()

    # Upstream Model forwards generate through __getattr__, so it is absent from dir(Model).
    runtime.generate = MagicMock(side_effect=generate)
    monkeypatch.setattr(mlx_stt, "serialized_mlx_runtime", guard)
    monkeypatch.setattr(mlx_stt, "resolve_model_snapshot", resolve)
    monkeypatch.setattr(mlx_audio.stt.utils, "load", load)
    monkeypatch.setattr(mlx_stt, "_runtime_cache", GuardedCache())
    for revision in [REVISION, REVISION, "c" * 40]:
        result = mlx_stt.transcribe_audio(np.zeros(16000), "Italian", model_revision=revision, model_id=model_id)
        assert result.transcript == "Ciao mondo."
    mlx_stt.clear_runtime_cache()
    assert events.count(("resolve", REVISION)) == 1
    assert events.count(("resolve", "c" * 40)) == 1
    assert events[-3:] == ["enter", "clear", "exit"]
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "output",
    [object(), STTOutput(text="", segments=[]), STTOutput(text="hello", segments=[{"text": "", "start": 0, "end": 1}])],
)
def test_invalid_upstream_results_are_product_errors(monkeypatch, output):
    runtime = MagicMock()
    runtime.generate.return_value = output
    monkeypatch.setattr(mlx_stt, "_get_runtime", lambda *args: runtime)
    with pytest.raises(GenerationError):
        mlx_stt.transcribe_audio(np.zeros(16000), "English", model_revision=REVISION)


CONSOLE_CODE = """
from unittest.mock import MagicMock
from mlx_audio.stt.models.base import STTOutput
from voices.adapter import mlx_stt
from voices.cli_entrypoint import main
from voices import runtime_identity
# Source-only tests need no built/installed Voices wheel or studio bundle.
package_version = runtime_identity.version
runtime_identity.version = lambda name: 'source-test' if name == 'voices' else package_version(name)
runtime = MagicMock()
def generate(audio, language, verbose):
    print('upstream stdout must not contaminate JSON')
    return STTOutput(text={'English': 'Hello world.', 'Italian': 'Ciao mondo.'}[language], segments=[])
runtime.generate.side_effect = generate
mlx_stt._get_runtime = lambda *args: runtime
main()
"""


def _console(tmp_path, arguments, *, code="from voices.cli_entrypoint import main; main()"):
    return subprocess.run(
        [sys.executable, "-c", code, "--json", "transcribe", *arguments],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "HF_HUB_OFFLINE": "1",
            "VOICES_LIBRARY": str(tmp_path / "untouched-library"),
        },
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg not installed")
@pytest.mark.parametrize("language,transcript", [("English", "Hello world."), ("Italian", "Ciao mondo.")])
def test_real_console_normalizes_wav_and_never_creates_library_or_output(tmp_path, language, transcript):
    audio = _wav(tmp_path / "speech.wav")
    before = audio.read_bytes()
    result = _console(
        tmp_path,
        ["--audio", str(audio), "--language", language, "--model-revision", REVISION],
        code=CONSOLE_CODE,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["transcript"] == transcript
    assert payload["audio"]["sha256"] == hashlib.sha256(before).hexdigest()
    assert payload["audio"]["normalized_sha256"] == hashlib.sha256(np.zeros(16000, dtype="<f4").tobytes()).hexdigest()
    assert payload["model_revision"] == REVISION
    assert Path(payload["runtime"]["executable"]).resolve() == Path(sys.executable).resolve()
    assert audio.read_bytes() == before
    assert list(tmp_path.iterdir()) == [audio]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg not installed")
def test_real_console_generation_error_has_one_json_envelope(tmp_path):
    audio = _wav(tmp_path / "speech.wav")
    before = audio.read_bytes()
    code = CONSOLE_CODE.replace(
        "runtime.generate.side_effect = generate",
        "runtime.generate.side_effect = RuntimeError('test inference failure')",
    )
    result = _console(
        tmp_path, ["--audio", str(audio), "--language", "English", "--model-revision", REVISION], code=code
    )
    assert result.returncode == 4
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "generation"
    assert payload["error"]["exit_code"] == 4
    assert "test inference failure" in payload["error"]["message"]
    assert audio.read_bytes() == before
    assert list(tmp_path.iterdir()) == [audio]


@pytest.mark.parametrize(
    "arguments,message",
    [
        ([], "audio"),
        (["--audio", "speech.wav"], "language"),
        (["--audio", "speech.wav", "--language", "English"], "model_revision"),
        (["--text-file", "script.txt"], "No such option"),
        (["--audio", "speech.wav", "--language", "English", "--model-revision", "main"], "40-character"),
        (["--audio", "missing.wav", "--language", "English", "--model-revision", REVISION], "existing WAV"),
    ],
)
def test_real_console_input_errors_are_one_json_document(tmp_path, arguments, message):
    result = _console(tmp_path, arguments)
    assert result.returncode == 2
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["exit_code"] == 2
    assert message in payload["error"]["message"]
    assert list(tmp_path.iterdir()) == []
