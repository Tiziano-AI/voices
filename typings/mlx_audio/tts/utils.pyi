from pathlib import Path

from mlx_audio.tts.models.qwen3_tts.qwen3_tts import Model

def load_model(model_path: Path, lazy: bool = False, strict: bool = True, **kwargs: object) -> Model: ...
