"""Adopted decoder equivalence and the upstream ICL cache identity defect."""

import ast
import inspect
import textwrap
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from mlx_audio.utils import load_audio

from voices.adapter import mlx_qwen, mlx_runtime
from voices.domain.errors import GenerationError


@pytest.mark.parametrize("source_rate", [16000, 24000, 48000])
def test_owned_bytes_decode_matches_native_path_loader_for_stereo_resampling(tmp_path, monkeypatch, source_rate):
    path = tmp_path / "stereo.wav"
    samples = np.arange(512, dtype=np.int16).reshape(256, 2) - 256
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(source_rate)
        handle.writeframes(samples.tobytes())
    native = np.array(load_audio(str(path), sample_rate=24000))
    runtime = MagicMock()
    runtime.sample_rate = 24000

    def generate(**kwargs):
        assert mlx_runtime._runtime_lock.locked()
        decoded = np.array(kwargs["ref_audio"])
        assert decoded.ndim == 1 and decoded.dtype == np.float32
        np.testing.assert_array_equal(decoded, native)
        yield SimpleNamespace(audio=decoded)

    runtime.generate.side_effect = generate
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda *_args: runtime)
    audio, rate = mlx_qwen.synthesize_reference_voice("Hello.", "English", path.read_bytes(), "Reference.")
    np.testing.assert_array_equal(audio, native)
    assert rate == 24000


def adopted_reference_encoder():
    """Exercise the adopted method's cache/encode prefix, without model weights."""
    source = textwrap.dedent(inspect.getsource(mlx_qwen.Qwen3TtsModel._prepare_icl_generation_inputs))
    method = ast.parse(source).body[0]
    assert isinstance(method, ast.FunctionDef)
    prefix = []
    for statement in method.body:
        # Stop only after the actual cache write, before target-text embeddings.
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "target_chat" for target in statement.targets
        ):
            break
        prefix.append(statement)
    else:
        pytest.fail("Upstream ICL preparation changed; review its reference-cache contract.")
    prefix.append(ast.Return(value=ast.Name(id="ref_codes", ctx=ast.Load())))
    args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=name) for name in ("self", "ref_audio", "ref_text")],
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[],
    )
    function = ast.FunctionDef(name="encode_reference", args=args, body=prefix, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {"mx": SimpleNamespace(array=np.array, eval=lambda *_args: None)}
    exec(compile(module, "<adopted-icl-cache-prefix>", "exec"), namespace)
    return namespace["encode_reference"]


def test_adapter_prevents_adopted_equal_size_sum_cache_collision_without_discarding_model(monkeypatch):
    encode_reference = adopted_reference_encoder()
    encoded = []

    def encode(audio):
        encoded.append(np.array(audio).copy())
        return np.array(audio).copy()

    runtime = SimpleNamespace(
        tokenizer=SimpleNamespace(encode=lambda _text: np.arange(8)),
        config=SimpleNamespace(talker_config=SimpleNamespace()),
        speech_tokenizer=SimpleNamespace(encode=encode),
        _icl_cache={},
        sample_rate=24000,
    )
    first, second = np.array([1, -1, 2, -2], dtype=np.float32), np.array([2, -2, 1, -1], dtype=np.float32)
    assert first.size == second.size and first.sum() == second.sum()
    # Demonstrate the real adopted defect; this is not our reconstruction of its key.
    np.testing.assert_array_equal(
        encode_reference(runtime, first, "Same transcript."), encode_reference(runtime, second, "Same transcript.")
    )
    assert len(encoded) == 1
    encoded.clear()
    runtime._icl_cache.clear()
    loads = []

    def get_runtime(*args):
        assert mlx_runtime._runtime_lock.locked()
        loads.append(args)
        return runtime

    def generate(**kwargs):
        assert mlx_runtime._runtime_lock.locked()
        codes = encode_reference(runtime, np.array(kwargs["ref_audio"]), kwargs["ref_text"])
        yield SimpleNamespace(audio=codes.flatten())
        assert mlx_runtime._runtime_lock.locked()

    runtime.generate = generate
    monkeypatch.setattr(mlx_qwen, "_runtime_cache", {})
    monkeypatch.setattr(mlx_qwen, "_load_runtime", get_runtime)
    monkeypatch.setattr(
        mlx_qwen, "read_audio", lambda data, **_kwargs: (first if data.getvalue() == b"first" else second, 24000)
    )
    one = mlx_qwen.synthesize_reference_voice("One.", "English", b"first", "Same transcript.")[0]
    two = mlx_qwen.synthesize_reference_voice("Two.", "English", b"second", "Same transcript.")[0]
    np.testing.assert_array_equal(one, first)
    np.testing.assert_array_equal(two, second)
    assert len(encoded) == 2 and len(loads) == 1
    assert list(mlx_qwen._runtime_cache.values()) == [runtime]
    assert not mlx_runtime._runtime_lock.locked()


def test_decoder_failure_releases_runtime_and_never_generates(monkeypatch):
    runtime = MagicMock()
    runtime.sample_rate = 24000
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda *_args: runtime)
    with pytest.raises(GenerationError, match="Base generation failed"):
        mlx_qwen.synthesize_reference_voice("One.", "English", b"not a WAV", "Reference.")
    runtime.generate.assert_not_called()
    assert not mlx_runtime._runtime_lock.locked()
