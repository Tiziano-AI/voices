"""Immutable Hugging Face snapshot selection shared by every model adapter."""

import re
from pathlib import Path
from typing import Protocol, cast

import huggingface_hub

from voices.domain.errors import GenerationError, InvalidInputError


class _SnapshotHub(Protocol):
    """The typed public Hub overload used here, excluding unrelated optional APIs."""

    def snapshot_download(self, *, repo_id: str, revision: str) -> str: ...


_hub = cast(_SnapshotHub, huggingface_hub)


def require_model_revision(revision: str) -> str:
    """Accept only a complete commit SHA, never a mutable branch or tag."""
    if re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
        raise InvalidInputError("model revision must be a full 40-character hexadecimal commit SHA.")
    return revision.lower()


def resolve_model_snapshot(model_id: str, revision: str) -> Path:
    """Resolve one exact commit in the standard shared HF cache, including offline mode.

    Passing the commit itself avoids resolving or publishing refs/main. The
    caller owns the process-global MLX lock across resolution, load and use.
    """
    revision = require_model_revision(revision)
    try:
        snapshot = Path(_hub.snapshot_download(repo_id=model_id, revision=revision)).resolve()
    except Exception as exc:
        raise GenerationError(f"Cannot resolve model '{model_id}' at revision '{revision}': {exc}") from exc
    if snapshot.name != revision or snapshot.parent.name != "snapshots" or not snapshot.is_dir():
        raise GenerationError(f"Model '{model_id}' did not resolve to the requested immutable snapshot '{revision}'.")
    return snapshot
