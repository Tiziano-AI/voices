from pathlib import Path

from mlx_audio.stt.models.qwen3_asr.qwen3_asr import Model
from mlx_audio.stt.models.qwen3_forced_aligner import Model as AlignerModel

def load(
    model_path: str | Path, lazy: bool = False, strict: bool = False, **kwargs: object
) -> Model | AlignerModel: ...
