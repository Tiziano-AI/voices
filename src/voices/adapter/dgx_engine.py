"""Retained CUDA operations, imported only in the offline GPU container.

Only standard-library imports occur at module import. This worker does not
import Voices or its MLX-dependent Mac wheel.
"""

import hashlib
import importlib.metadata as metadata
import json
import platform
import sys
import time
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path("/job")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def measure(call: Callable[[], Any]) -> tuple[Any, float]:
    torch: Any = import_module("torch")

    torch.cuda.synchronize()
    start = time.monotonic()
    value = call()
    torch.cuda.synchronize()
    return value, time.monotonic() - start


def runtime(request: dict[str, Any]) -> dict[str, Any]:
    torch: Any = import_module("torch")

    base = json.loads(Path("/occurrence/base-torch.json").read_bytes())
    actual: dict[str, Any] = {
        "metadata_version": metadata.version("torch"),
        "imported_version": str(torch.__version__),
        "module_path": str(Path(torch.__file__).resolve()),
        "module_sha256": sha(Path(torch.__file__).read_bytes()),
        "extension_path": str(Path(torch._C.__file__).resolve()),
        "extension_sha256": sha(Path(torch._C.__file__).read_bytes()),
        "cuda_compiled": torch.version.cuda,
    }
    if actual != base:
        raise RuntimeError("Retained CUDA/Torch overlay identity changed")
    tts = request["operation"] in ("design", "base")
    if tts:
        torch.backends.cudnn.enabled = False
    if metadata.version("transformers") != ("4.57.3" if tts else "5.13.0"):
        raise RuntimeError("Retained Transformers identity changed")
    names = ("torch", "transformers", "numpy", "soundfile") + (("qwen-tts",) if tts else ())
    source = b"".join((ROOT / name).read_bytes() for name in ("dgx_worker.py", "dgx_engine.py"))
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "voices_version": request["voices_version"],
        "source_sha256": sha(source),
        "source_scope": "dgx-worker-source-at-execution",
        "packages": {name: metadata.version(name) for name in names},
        "package_scope": "selected-runtime-dependencies",
        "compute": {
            "backend": "dgx",
            "invocation": request["invocation"],
            "model_id": request["model_id"],
            "model_revision": request["revision"],
            "image": request["image"],
            "cuda": actual,
            "controls": {
                "dtype": "bfloat16",
                "attention": "sdpa",
                "offline": True,
                "non_streaming_mode": True if tts else None,
                "cudnn_enabled": bool(torch.backends.cudnn.enabled),
            },
        },
    }


def tts(request: dict[str, Any], checkpoint: str) -> dict[str, Any]:
    import numpy as np

    sf: Any = import_module("soundfile")
    torch: Any = import_module("torch")
    Qwen3TTSModel: Any = import_module("qwen_tts").Qwen3TTSModel

    torch.backends.cudnn.enabled = False
    model, load = measure(
        lambda: Qwen3TTSModel.from_pretrained(
            checkpoint, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True
        )
    )
    common: dict[str, Any] = {"text": request["text"], "language": request["language"], "non_streaming_mode": True}

    def call() -> Any:
        if request["operation"] == "design":
            return model.generate_voice_design(**common, instruct=request["instruct"])
        return model.generate_voice_clone(
            **common, ref_audio=str(ROOT / "input.audio"), ref_text=request["reference_text"], x_vector_only_mode=False
        )

    (wavs, rate), generation = measure(call)
    audio = np.asarray(wavs[0], dtype=np.float32)
    if len(wavs) != 1 or audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError("Invalid complete mono audio")
    sf.write(ROOT / "output.wav", audio, rate, subtype="FLOAT")
    return {
        "audio_sha256": sha((ROOT / "output.wav").read_bytes()),
        "sample_rate": rate,
        "duration_seconds": len(audio) / rate,
        "load_seconds": load,
        "generation_seconds": generation,
    }


def recognize_or_align(request: dict[str, Any], checkpoint: str) -> dict[str, Any]:
    import numpy as np

    torch: Any = import_module("torch")
    transformers: Any = import_module("transformers")

    audio = np.frombuffer((ROOT / "input.audio").read_bytes(), dtype="<f4").copy()
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError("Invalid normalized mono float32 audio")
    processor = transformers.AutoProcessor.from_pretrained(checkpoint, local_files_only=True)
    cls = (
        transformers.Qwen3ASRForConditionalGeneration
        if request["operation"] == "asr"
        else transformers.AutoModelForTokenClassification
    )
    model, load = measure(
        lambda: cls.from_pretrained(
            checkpoint, dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True
        ).to("cuda:0")
    )
    if request["operation"] == "asr":
        if any(request.get(key) is not None for key in ("text", "reference_text", "instruct")):
            raise ValueError("ASR must be audio-only")
        inputs = processor.apply_transcription_request(
            audio=audio, language=request["language"], sampling_rate=16000
        ).to(model.device, model.dtype)
        with torch.inference_mode():
            generated, elapsed = measure(lambda: model.generate(**inputs))
        continuation = generated[:, inputs["input_ids"].shape[1] :]
        parsed = processor.decode(continuation[0], return_format="parsed")
        return {
            "transcript": parsed["transcription"],
            "load_seconds": load,
            "generation_seconds": elapsed,
            "expected_text_provided": False,
            "new_tokens": int(continuation.shape[1]),
        }
    inputs, word_lists = processor.prepare_forced_aligner_inputs(
        audio=audio, transcript=request["text"], language=request["language"], sampling_rate=16000
    )
    inputs = inputs.to(model.device, model.dtype)
    with torch.inference_mode():
        output, elapsed = measure(lambda: model(**inputs))
    words = processor.decode_forced_alignment(
        logits=output.logits,
        input_ids=inputs["input_ids"],
        word_lists=word_lists,
        timestamp_token_id=model.config.timestamp_token_id,
    )[0]
    # Retained Transformers 5.13 returns start_time/end_time; Voices owns start/end.
    mapped = [{"text": item["text"], "start": item["start_time"], "end": item["end_time"]} for item in words]
    return {"words": mapped, "load_seconds": load, "generation_seconds": elapsed, "spoken_content_verified": False}


def main() -> None:
    request_bytes = (ROOT / "request.json").read_bytes()
    request = json.loads(request_bytes)
    if request.get("audio_sha256") and sha((ROOT / "input.audio").read_bytes()) != request["audio_sha256"]:
        raise ValueError("Audio bytes differ from captured request")
    if (
        request.get("reference_text_sha256")
        and sha(request["reference_text"].encode()) != request["reference_text_sha256"]
    ):
        raise ValueError("Approved reference transcript differs from request")
    checkpoint = str(Path("/models/snapshots") / request["revision"])
    started = time.monotonic()
    identity = runtime(request)
    result = (
        tts(request, checkpoint)
        if request["operation"] in ("design", "base")
        else recognize_or_align(request, checkpoint)
    )
    result.update(runtime=identity, request_sha256=sha(request_bytes), compute_seconds=time.monotonic() - started)
    with (ROOT / "result.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    main()
