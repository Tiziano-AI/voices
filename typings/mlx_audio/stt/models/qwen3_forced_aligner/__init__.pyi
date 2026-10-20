from dataclasses import dataclass

import numpy as np

@dataclass(frozen=True)
class ForcedAlignItem:
    text: str
    start_time: float
    end_time: float

@dataclass(frozen=True)
class ForcedAlignResult:
    items: list[ForcedAlignItem]

class Model:
    def generate(self, audio: np.ndarray, text: str, language: str) -> ForcedAlignResult: ...
