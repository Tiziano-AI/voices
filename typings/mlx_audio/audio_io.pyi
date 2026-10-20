import io
from pathlib import Path

import numpy as np

def read(
    file: str | Path | io.BytesIO,
    always_2d: bool = False,
    dtype: str = "float64",
    sample_rate: int | None = None,
    nchannels: int | None = None,
) -> tuple[np.ndarray, int]: ...
