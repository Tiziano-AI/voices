import os
from pathlib import Path

from voices.domain.contracts import DEFAULT_LANGUAGE_LABEL

VOICE_DESIGN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"
VOICE_DESIGN_MODEL_REVISION = "7d3824abff87e49756bb0f83fb5411de75d160c4"
BASE_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
BASE_MODEL_REVISION = "a6eb4f68e4b056f1215157bb696209bc82a6db48"
STT_MODEL = "mlx-community/Qwen3-ASR-1.7B-bf16"
STT_MODEL_REVISION = "e1f6c266914abc5a46e8756e02580f834a6cf8a7"
ALIGNER_MODEL = "mlx-community/Qwen3-ForcedAligner-0.6B-bf16"
ALIGNER_MODEL_REVISION = "53c8c0e46733eec430e4b53dd6471d0e5dee45f8"
ALIGNER_SAMPLE_RATE = 16_000

DEFAULT_LIBRARY = Path.home() / ".voices"
DEFAULT_OUTPUT_DIR = Path("./outputs")
DEFAULT_LANGUAGE = DEFAULT_LANGUAGE_LABEL
FALLBACK_SAMPLE_RATE = 24_000
STT_SAMPLE_RATE = 16_000
GUIDED_RECORD_TARGET_SECONDS = 30.0
FREE_RECORD_MINIMUM_SECONDS = 3.0
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def get_library_path(cli_override: Path | None = None) -> Path:
    """Return the canonical effective library root from CLI override, env, or product default."""
    if cli_override is not None:
        selected = cli_override
    else:
        env = os.environ.get("VOICES_LIBRARY")
        selected = Path(env) if env else DEFAULT_LIBRARY
    return selected.expanduser().resolve(strict=False)
