#!/usr/bin/env python3
"""Run hermetic checks for the repo-owned voices-local-studio skill."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "voices-local-studio"
SKILL_ROOT = REPO_ROOT / "skills" / SKILL_NAME


def main() -> int:
    """Run all skill package checks."""

    for command in skill_check_commands():
        completed = subprocess.run(
            command,
            cwd=SKILL_ROOT,
            env=skill_env(),
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


def skill_check_commands() -> list[list[str]]:
    """Return the hermetic skill package check command sequence."""

    with_deps = ["uv", "run", "--locked", "--project", str(REPO_ROOT)]
    return [
        [*with_deps, "ruff", "check", "scripts", "tests"],
        [*with_deps, "ruff", "format", "--check", "scripts", "tests"],
        [
            *with_deps,
            "basedpyright",
            "--project",
            "basedpyrightconfig.json",
            "--level",
            "error",
        ],
        [*with_deps, "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        [*with_deps, "python", "scripts/check_generated_artifacts.py"],
    ]


def skill_env() -> dict[str, str]:
    """Return the external environment and cache settings for skill checks."""

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SKILL_ROOT / "scripts")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["RUFF_CACHE_DIR"] = str(REPO_ROOT / ".ruff_cache" / "skill")
    return env


if __name__ == "__main__":
    raise SystemExit(main())
