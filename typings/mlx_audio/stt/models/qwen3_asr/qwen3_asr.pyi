import numpy as np
from mlx_audio.stt.models.base import STTOutput

class Model:
    def generate(self, audio: np.ndarray, *, language: str, verbose: bool = False) -> STTOutput: ...
