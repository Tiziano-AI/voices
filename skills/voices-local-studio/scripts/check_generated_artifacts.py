#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

BAD_DIR_NAMES = {".venv", ".ruff_cache", ".pytest_cache", "__pycache__"}
BAD_FILE_NAMES = {".DS_Store", "pyproject.toml", "uv.lock"}
BAD_SUFFIXES = {".pyc", ".pyo"}


def generated_artifacts(root: Path) -> list[str]:
    """Return generated files or nested project artifacts that do not belong in the skill package."""
    found: list[str] = []
    for path in root.rglob("*"):
        # Finder metadata is not skill content; directories and links still fail.
        if path.name == ".DS_Store" and not path.is_symlink() and path.is_file():
            continue
        bad_name = path.name in BAD_DIR_NAMES or path.name in BAD_FILE_NAMES
        bad_suffix = path.is_file() and path.suffix in BAD_SUFFIXES
        if bad_name or bad_suffix:
            found.append(str(path.relative_to(root)))
    return sorted(found)


def main() -> int:
    """Check the current skill package and report generated artifacts as JSON."""
    root = Path(__file__).resolve().parents[1]
    found = generated_artifacts(root)
    print(json.dumps({"generated_artifacts": found}, indent=2))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
