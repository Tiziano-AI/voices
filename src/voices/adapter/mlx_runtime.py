"""Shared MLX runtime coordination for local model adapters."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

_runtime_lock = Lock()


@contextmanager
def serialized_mlx_runtime() -> Iterator[None]:
    """Serialize MLX model loading and generation inside one process.

    The local MLX audio runtime is not safe to enter concurrently from the
    AnyIO worker pool used by the browser edge. Keep the lock at the adapter
    boundary so every CLI and UI path shares the same Metal command queue guard.
    """
    with _runtime_lock:
        yield
