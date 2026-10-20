#!/usr/bin/env python3
"""Enforce repository-owned file size guardrails."""

from pathlib import Path

MAX_BYTES = 18 * 1024
MAX_LINES = 500
CHECK_SUFFIXES = frozenset((".md", ".mjs", ".py", ".toml", ".ts", ".tsx"))
EXCLUDED_PARTS = frozenset(
    (
        ".cdx-continue",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tmp",
        ".venv",
        "dist",
        "node_modules",
        "outputs",
        "playwright-report",
        "storyshots",
        "test-results",
    )
)
REPO_ROOT = Path(__file__).resolve().parent.parent


def is_checked_file(path: Path) -> bool:
    """Return whether one file belongs to the guardrail-owned source set."""
    relative = path.relative_to(REPO_ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    return path.suffix in CHECK_SUFFIXES


def line_count(path: Path) -> int:
    """Return the number of physical lines in one UTF-8 compatible source file."""
    return len(path.read_text(encoding="utf-8").splitlines())


def main() -> int:
    """Print all guardrail violations and return non-zero when any file is too large."""
    violations: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or not is_checked_file(path):
            continue
        byte_count = path.stat().st_size
        lines = line_count(path)
        if lines > MAX_LINES or byte_count > MAX_BYTES:
            violations.append(f"{path.relative_to(REPO_ROOT)}: {lines} lines, {byte_count} bytes")
    if violations:
        print("Files exceed the 500-line or 18 KiB guardrail:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
