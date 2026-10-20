from collections.abc import Iterable

import mlx.core as mx
from mlx_audio.tts.models.base import GenerationResult

class Model:
    sample_rate: int
    _icl_cache: dict[object, object]
    def generate_voice_design(
        self,
        *,
        text: str,
        instruct: str,
        language: str,
        verbose: bool = False,
    ) -> Iterable[GenerationResult]: ...
    def generate(
        self,
        *,
        text: str,
        ref_audio: str | mx.array,
        ref_text: str,
        lang_code: str,
        verbose: bool = False,
    ) -> Iterable[GenerationResult]: ...
