"""Generation-time identity of installed Voices source and selected dependencies."""

import hashlib
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from voices.domain.errors import MissingDependencyError

# This deliberately named selected set is not a complete dependency lockfile.
SELECTED_RUNTIME_PACKAGES = (
    "huggingface-hub",
    "miniaudio",
    "mlx",
    "mlx-audio",
    "mlx-metal",
    "numpy",
    "pydantic",
    "scipy",
    "tokenizers",
    "transformers",
)


class ComputeRuntimeIdentity(BaseModel):
    """Actual optional remote checkpoint and controls; no client MLX attribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["dgx"]
    invocation: str = Field(pattern=r"^[0-9a-f]{32}$")
    model_id: str
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    image: str
    cuda: dict[str, JsonValue]
    controls: dict[str, JsonValue]


class RuntimeIdentity(BaseModel):
    """Portable source identity plus the actual interpreter and dependency versions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    python: str
    executable: str
    platform: str
    voices_version: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_scope: Literal["installed-python-source-at-observation", "dgx-worker-source-at-execution"] = (
        "installed-python-source-at-observation"
    )
    packages: dict[str, str]
    package_scope: Literal["selected-runtime-dependencies"] = "selected-runtime-dependencies"
    compute: ComputeRuntimeIdentity | None = None


def source_sha256(package_root: Path) -> str:
    """Hash relative paths and exact .py bytes, independent of installation location."""
    digest = hashlib.sha256()
    paths = sorted(
        path
        for path in package_root.rglob("*.py")
        if path.is_file() and not {"__pycache__", "web_dist"}.intersection(path.relative_to(package_root).parts)
    )
    if not paths:
        raise RuntimeError(f"No Voices Python source found under '{package_root}'.")
    for path in paths:
        relative = path.relative_to(package_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def get_runtime_identity() -> RuntimeIdentity:
    """Observe this installed package before inference; never invent missing versions."""
    try:
        return RuntimeIdentity(
            python=platform.python_version(),
            executable=sys.executable,
            platform=platform.platform(),
            voices_version=version("voices"),
            source_sha256=source_sha256(Path(__file__).resolve().parent),
            packages={name: version(name) for name in SELECTED_RUNTIME_PACKAGES},
        )
    except (OSError, RuntimeError, PackageNotFoundError) as exc:
        raise MissingDependencyError(f"Cannot establish the installed Voices runtime identity: {exc}") from exc
