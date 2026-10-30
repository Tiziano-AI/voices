"""Explicit per-invocation compute selection; storage and devices stay on Mac."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from voices import config
from voices.domain.errors import InvalidInputError

Operation = Literal["design", "base", "asr", "align"]
DGX_MODELS: dict[Operation, tuple[str, str]] = {
    "design": ("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "5ecdb67327fd37bb2e042aab12ff7391903235d3"),
    "base": ("Qwen/Qwen3-TTS-12Hz-1.7B-Base", "fd4b254389122332181a7c3db7f27e918eec64e3"),
    "asr": ("Qwen/Qwen3-ASR-1.7B-hf", "bcd2b5b7f32b480ab5790554cfa8347f246a14f3"),
    "align": ("Qwen/Qwen3-ForcedAligner-0.6B-hf", "c07281df297b9905d24a508279258cccf987a064"),
}


@dataclass(frozen=True, slots=True)
class ComputeSelection:
    """No environment/global default mutation or automatic fallback."""

    backend: Literal["mlx", "dgx"] = "mlx"
    ssh_host: str | None = None
    ssh_config: Path | None = None
    state_root: Path = Path("~/.local/state/voices/compute")

    def __post_init__(self) -> None:
        if self.backend not in ("mlx", "dgx"):
            raise InvalidInputError("Compute must be mlx or dgx.")
        if self.backend == "dgx" and (
            not self.ssh_host
            or self.ssh_host.startswith("-")
            or not self.ssh_host.replace("-", "").replace(".", "").isalnum()
        ):
            raise InvalidInputError("DGX compute requires an explicit SSH host alias.")
        if self.backend == "mlx" and (self.ssh_host is not None or self.ssh_config is not None):
            raise InvalidInputError("SSH options require --compute dgx.")

    def model(self, operation: Operation, revision: str | None = None) -> tuple[str, str]:
        """Resolve the selected checkpoint, never borrow the other backend's SHA."""
        if self.backend == "dgx":
            model, pinned = DGX_MODELS[operation]
        else:
            model, pinned = {
                "design": (config.VOICE_DESIGN_MODEL, config.VOICE_DESIGN_MODEL_REVISION),
                "base": (config.BASE_MODEL, config.BASE_MODEL_REVISION),
                "asr": (config.STT_MODEL, config.STT_MODEL_REVISION),
                "align": (config.ALIGNER_MODEL, config.ALIGNER_MODEL_REVISION),
            }[operation]
        if revision is not None:
            if self.backend == "dgx" and revision != pinned:
                raise InvalidInputError("DGX compute uses only its retained pinned checkpoint revision.")
            pinned = revision
        return model, pinned

    def describe(self) -> dict[str, object]:
        """Configuration is not a receipt of remote readiness or inference."""
        return {
            "backend": self.backend,
            "ssh_host": self.ssh_host,
            "models": {
                operation: {"id": self.model(operation)[0], "revision": self.model(operation)[1]}
                for operation in ("design", "base", "asr", "align")
            },
            "automatic_fallback": False,
            "remote_readiness_observed": False,
        }


LOCAL_COMPUTE = ComputeSelection()
