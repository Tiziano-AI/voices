import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest for one local file without mutating it."""
    h = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(8192):
            h.update(chunk)
    return h.hexdigest()
