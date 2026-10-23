#!/usr/bin/env python3
"""Canonical repository gate for voices."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = [
    ["uv", "run", "python", "devtools/sync_skill.py", "--validate-source"],
    ["uv", "run", "python", "devtools/check_skill.py"],
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "ruff", "format", "--check", "."],
    ["uv", "run", "python", "devtools/check_file_size.py"],
    ["pnpm", "--dir", "web", "exec", "basedpyright", "--project", ".."],
    ["uv", "run", "pytest", "tests/", "-v"],
    ["pnpm", "--dir", "web", "lint"],
    ["pnpm", "--dir", "web", "build"],
    ["pnpm", "--dir", "web", "acceptance"],
]


def main() -> int:
    """Run the canonical gate commands from repository root."""
    for command in COMMANDS:
        print(f"+ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
