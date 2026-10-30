"""Retained Transformers 5.13 processor contracts, without CUDA/model work."""

from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from voices.adapter import dgx_engine as engine


class Inputs(dict):
    def to(self, *_args):
        return self


@pytest.mark.parametrize("operation", ["asr", "align"])
def test_retained_processor_output_mapping_and_audio_only_boundary(tmp_path, monkeypatch, operation):
    # Source oracle: retained processing_qwen3_asr.py decode:553/583 and
    # decode_forced_alignment:773-795. These are upstream keys, not Voices keys.
    (tmp_path / "input.audio").write_bytes(np.zeros(16000, dtype="<f4").tobytes())
    monkeypatch.setattr(engine, "ROOT", tmp_path)
    monkeypatch.setattr(engine, "measure", lambda call: (call(), 0.0))
    inputs = Inputs(input_ids=np.array([[1, 2]]))
    calls = []

    def transcription(**kwargs):
        calls.append(kwargs)
        return inputs

    processor = SimpleNamespace(
        apply_transcription_request=transcription,
        decode=lambda _value, **_kwargs: {"language": "Italian", "transcription": "Una frase."},
        prepare_forced_aligner_inputs=lambda **kwargs: (inputs, [["Una", "frase."]]),
        decode_forced_alignment=lambda **kwargs: [
            [
                {"text": "Una", "start_time": 0.1, "end_time": 0.3},
                {"text": "frase.", "start_time": 0.3, "end_time": 0.9},
            ]
        ],
    )

    class Model:
        device, dtype = "cuda:0", "bfloat16"
        config = SimpleNamespace(timestamp_token_id=3)

        def to(self, *_args):
            return self

        def generate(self, **_kwargs):
            return np.array([[1, 2, 4, 5]])

        def __call__(self, **_kwargs):
            return SimpleNamespace(logits="source-shaped logits")

    loader = SimpleNamespace(from_pretrained=lambda *args, **kwargs: Model())
    transformers = SimpleNamespace(
        AutoProcessor=SimpleNamespace(from_pretrained=lambda *args, **kwargs: processor),
        Qwen3ASRForConditionalGeneration=loader,
        AutoModelForTokenClassification=loader,
    )
    torch = SimpleNamespace(bfloat16="bfloat16", inference_mode=nullcontext)
    monkeypatch.setattr(engine, "import_module", lambda name: {"torch": torch, "transformers": transformers}[name])
    request = {"operation": operation, "language": "Italian", "text": None if operation == "asr" else "Una frase."}
    result = engine.recognize_or_align(request, "/retained/snapshot")
    if operation == "asr":
        assert result["transcript"] == "Una frase." and result["expected_text_provided"] is False
        assert set(calls[0]) == {"audio", "language", "sampling_rate"}
        request["text"] = "Not allowed."
        with pytest.raises(ValueError, match="audio-only"):
            engine.recognize_or_align(request, "/retained/snapshot")
    else:
        assert result["words"] == [
            {"text": "Una", "start": 0.1, "end": 0.3},
            {"text": "frase.", "start": 0.3, "end": 0.9},
        ]
        assert result["spoken_content_verified"] is False
