import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from unittest.mock import MagicMock

import numpy as np
import pytest
from helpers import MOCK_AUDIO

from voices.adapter import mlx_qwen, mlx_runtime
from voices.domain.errors import GenerationError
from voices.store.library_store import write_wav


@pytest.fixture
def reference_audio(tmp_path):
    path = tmp_path / "reference.wav"
    write_wav(path, MOCK_AUDIO, 24000)
    return path.read_bytes()


def test_design_reference_audio_calls_voice_design(monkeypatch):
    runtime = MagicMock()
    runtime.sample_rate = 22050
    runtime.generate_voice_design.return_value = [MagicMock(audio=MOCK_AUDIO)]
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)

    audio, sample_rate = mlx_qwen.design_reference_audio(
        text="Hello world.",
        instruct="Low narrator",
        language="English",
    )

    assert sample_rate == 22050
    assert audio.shape == MOCK_AUDIO.shape
    runtime.generate_voice_design.assert_called_once_with(
        text="Hello world.",
        instruct="Low narrator",
        language="English",
        verbose=False,
    )


def test_synthesize_reference_voice_uses_lang_code(monkeypatch, reference_audio):
    runtime = MagicMock()
    runtime.sample_rate = 24000
    runtime.generate.return_value = [MagicMock(audio=MOCK_AUDIO)]
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)

    mlx_qwen.synthesize_reference_voice(
        text="Hello world.",
        language="Italian",
        reference_audio=reference_audio,
        reference_text="Ciao mondo.",
    )

    runtime.generate.assert_called_once_with(
        text="Hello world.",
        ref_audio=runtime.generate.call_args.kwargs["ref_audio"],
        ref_text="Ciao mondo.",
        lang_code="Italian",
        verbose=False,
    )
    np.testing.assert_array_equal(np.array(runtime.generate.call_args.kwargs["ref_audio"]), MOCK_AUDIO)
    runtime._icl_cache.clear.assert_called_once_with()


def test_synthesize_reference_voice_serializes_runtime_generate(monkeypatch, reference_audio):
    runtime = MagicMock()
    runtime.sample_rate = 24000
    entered_generate = Event()
    release_generate = Event()
    active_generate = Lock()
    overlap_detected = False

    def generate(**_kwargs: object) -> list[MagicMock]:
        nonlocal overlap_detected
        acquired = active_generate.acquire(blocking=False)
        if not acquired:
            overlap_detected = True
            return [MagicMock(audio=MOCK_AUDIO)]
        try:
            entered_generate.set()
            release_generate.wait(timeout=2)
            return [MagicMock(audio=MOCK_AUDIO)]
        finally:
            active_generate.release()

    runtime.generate.side_effect = generate
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            mlx_qwen.synthesize_reference_voice,
            text="First.",
            language="English",
            reference_audio=reference_audio,
            reference_text="Reference.",
        )
        assert entered_generate.wait(timeout=1)
        second = pool.submit(
            mlx_qwen.synthesize_reference_voice,
            text="Second.",
            language="English",
            reference_audio=reference_audio,
            reference_text="Reference.",
        )
        time.sleep(0.05)
        assert not overlap_detected
        release_generate.set()
        assert first.result(timeout=1)[1] == 24000
        assert second.result(timeout=1)[1] == 24000

    assert not overlap_detected
    assert runtime.generate.call_count == 2


def test_design_reference_audio_raises_on_empty_result(monkeypatch):
    runtime = MagicMock()
    runtime.sample_rate = 24000
    runtime.generate_voice_design.return_value = iter(())
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)

    with pytest.raises(GenerationError, match="returned no audio"):
        mlx_qwen.design_reference_audio(
            text="Hello world.",
            instruct="Low narrator",
            language="English",
        )


def test_design_reference_audio_wraps_runtime_error(monkeypatch):
    runtime = MagicMock()
    runtime.generate_voice_design.side_effect = RuntimeError("metal failed")
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)

    with pytest.raises(GenerationError, match="VoiceDesign generation failed"):
        mlx_qwen.design_reference_audio(
            text="Hello world.",
            instruct="Low narrator",
            language="English",
        )


def test_synthesize_reference_voice_wraps_runtime_error(monkeypatch, reference_audio):
    runtime = MagicMock()
    runtime.generate.side_effect = RuntimeError("metal failed")
    runtime.sample_rate = 24000
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)

    with pytest.raises(GenerationError, match="Base generation failed"):
        mlx_qwen.synthesize_reference_voice(
            text="Hello world.",
            language="English",
            reference_audio=reference_audio,
            reference_text="Hello world.",
        )


@pytest.fixture(params=["design", "synthesize"])
def generate_audio(request, monkeypatch, reference_audio):
    """Exercise both product entrypoints without loading or running a model."""
    runtime = MagicMock()
    runtime.sample_rate = 24000
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda cache_key, model_id: runtime)

    def run(chunks):
        if request.param == "design":
            runtime.generate_voice_design.return_value = chunks
            return mlx_qwen.design_reference_audio("Hello.", "Warm narrator", "English")
        runtime.generate.return_value = chunks
        return mlx_qwen.synthesize_reference_voice("Hello.", "English", reference_audio, "Reference.")

    return run


@pytest.mark.parametrize("chunk_count", [1, 3])
def test_generation_retains_all_chunks_and_exhausts_under_runtime_lock(generate_audio, chunk_count):
    completed = False
    arrays = [np.array([index, index + 0.5], dtype=np.float64) for index in range(chunk_count)]

    def chunks():
        nonlocal completed
        for array in arrays:
            assert mlx_runtime._runtime_lock.locked()
            yield MagicMock(audio=array)
        # Upstream Qwen calls mx.clear_cache() after its final yield.
        assert mlx_runtime._runtime_lock.locked()
        completed = True

    audio, sample_rate = generate_audio(chunks())

    np.testing.assert_array_equal(audio, np.concatenate(arrays).astype(np.float32))
    assert audio.dtype == np.float32
    assert sample_rate == 24000
    assert completed
    assert not mlx_runtime._runtime_lock.locked()


def test_generation_does_not_publish_partial_audio_after_late_failure(generate_audio):
    def chunks():
        yield MagicMock(audio=MOCK_AUDIO)
        raise RuntimeError("generation tail failed")

    with pytest.raises(GenerationError, match="generation failed: generation tail failed"):
        generate_audio(chunks())
    assert not mlx_runtime._runtime_lock.locked()


@pytest.mark.parametrize("arrays", [[], [np.array([])], [MOCK_AUDIO, np.array([])]])
def test_generation_rejects_missing_or_empty_audio_chunks(generate_audio, arrays):
    with pytest.raises(GenerationError, match="returned no audio"):
        generate_audio(MagicMock(audio=array) for array in arrays)


def test_load_runtime_uses_upstream_tokenizer_without_global_patch(monkeypatch, tmp_path):
    from mlx_audio.tts import utils
    from transformers import AutoTokenizer

    runtime = MagicMock(spec=mlx_qwen.Qwen3TtsModel)
    original_from_pretrained = AutoTokenizer.from_pretrained

    def load_model(model_path):
        assert model_path == tmp_path
        assert AutoTokenizer.from_pretrained == original_from_pretrained
        return runtime

    monkeypatch.setattr(mlx_qwen, "resolve_model_snapshot", lambda _model_id, _revision: tmp_path)
    monkeypatch.setattr(utils, "load_model", load_model)

    assert mlx_qwen._load_runtime("test-model", "a" * 40) is runtime
