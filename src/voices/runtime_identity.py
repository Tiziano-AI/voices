"""Generation-time identity of installed Voices source and selected dependencies."""

import hashlib
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class RuntimeIdentity(BaseModel):
    """Portable source identity plus the actual interpreter and dependency versions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    python: str
    executable: str
    platform: str
    voices_version: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_scope: Literal["installed-python-source-at-observation"] = "installed-python-source-at-observation"
    packages: dict[str, str]
    package_scope: Literal["selected-runtime-dependencies"] = "selected-runtime-dependencies"


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
