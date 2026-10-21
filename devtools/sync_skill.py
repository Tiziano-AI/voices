#!/usr/bin/env python3
"""Sync the repo-owned voices-local-studio skill package to the live root."""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "voices-local-studio"
SOURCE_ROOT = REPO_ROOT / "skills" / SKILL_NAME
TARGET_ROOT = Path.home() / ".agents" / "skills" / SKILL_NAME
REQUIRED_SKILL_DESCRIPTION = (
    "Operate local Voices on this Mac: create/select/review voices, generate speech, "
    "transcribe an existing WAV, or align supplied text to audio. Not generic TTS/provider "
    "advice or skill-package authoring."
)
REQUIRED_SHORT_DESCRIPTION = "Operate voices, speech, transcription and word timing"
REQUIRED_DEFAULT_PROMPT = (
    "Use $voices-local-studio to operate the installed voices CLI for speech, voice creation/review, "
    "audio-only transcription or supplied-text alignment, preserving operator intent and recognition "
    "versus timing boundaries."
)

FORBIDDEN_NAMES = frozenset(
    (
        ".DS_Store",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "pyproject.toml",
        "uv.lock",
    )
)
FORBIDDEN_SUFFIXES = frozenset((".pyc", ".pyo"))
REQUIRED_FILES = (
    "SKILL.md",
    "basedpyrightconfig.json",
    "agents/openai.yaml",
    "assets/voices.svg",
    "assets/voices.png",
    "references/local-product-contract.md",
    "references/operator-recipes.md",
    "references/workflow-recipes.md",
    "references/voice-design-best-practices.md",
    "references/voice-clone-best-practices.md",
    "references/review-scenarios.md",
    "scripts/voice_prompt_workbench.py",
    "scripts/check_generated_artifacts.py",
    "tests/test_voice_workbench.py",
)
REQUIRED_METADATA = {
    ("interface", "display_name"): "Voices Local Studio",
    (
        "interface",
        "short_description",
    ): REQUIRED_SHORT_DESCRIPTION,
    (
        "interface",
        "default_prompt",
    ): REQUIRED_DEFAULT_PROMPT,
    ("interface", "icon_small"): "./assets/voices.svg",
    ("interface", "icon_large"): "./assets/voices.png",
    ("interface", "brand_color"): "#953D4E",
    ("policy", "allow_implicit_invocation"): "true",
}


class SyncSkillNamespace(argparse.Namespace):
    """Typed sync-skill CLI namespace."""

    check: bool
    validate_source: bool

    def __init__(self) -> None:
        """Initialize parser defaults."""

        super().__init__()
        self.check = False
        self.validate_source = False


def main() -> int:
    """Run skill package validation, sync, or sync verification."""

    namespace = parse_args()
    source_errors = validate_skill_package(SOURCE_ROOT)
    if source_errors:
        emit_errors("repo skill package is invalid", source_errors)
        return 1
    if namespace.validate_source:
        _ = sys.stdout.write("source skill package validation passed\n")
        return 0
    if namespace.check:
        target_errors = validate_skill_package(TARGET_ROOT)
        if target_errors:
            emit_errors("installed skill package is invalid", target_errors)
            return 1
        drift_errors = compare_skill_packages(source=SOURCE_ROOT, target=TARGET_ROOT)
        if drift_errors:
            emit_errors("installed skill package is out of sync", drift_errors)
            return 1
        _ = sys.stdout.write("skill package sync check passed\n")
        return 0
    sync_skill_package(source=SOURCE_ROOT, target=TARGET_ROOT)
    target_errors = validate_skill_package(TARGET_ROOT)
    if target_errors:
        emit_errors("synced skill package is invalid", target_errors)
        return 1
    _ = sys.stdout.write(f"synced {SOURCE_ROOT} -> {TARGET_ROOT}\n")
    return 0


def parse_args() -> SyncSkillNamespace:
    """Parse sync-skill arguments."""

    parser = argparse.ArgumentParser(description="Sync the repo-owned voices-local-studio skill.")
    mode = parser.add_mutually_exclusive_group()
    _ = mode.add_argument(
        "--check",
        action="store_true",
        help="verify package file bytes and executable bits, ignoring regular .DS_Store metadata files",
    )
    _ = mode.add_argument(
        "--validate-source",
        action="store_true",
        help="validate only the repository package without reading or writing an installed skill",
    )
    namespace = SyncSkillNamespace()
    _ = parser.parse_args(namespace=namespace)
    return namespace


def validate_skill_package(root: Path) -> list[str]:
    """Return structural, metadata, and contamination errors for a skill package."""

    errors: list[str] = []
    if not root.exists():
        return [f"missing skill package: {root}"]
    if not root.is_dir():
        return [f"skill package path is not a directory: {root}"]
    errors.extend(missing_required_files(root))
    errors.extend(forbidden_artifact_errors(root))
    if errors:
        return errors
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = parse_skill_frontmatter(skill_text)
    if frontmatter.get("name") != SKILL_NAME:
        errors.append("SKILL.md must declare name: voices-local-studio")
    if frontmatter.get("description") != REQUIRED_SKILL_DESCRIPTION:
        errors.append(f"SKILL.md description must be {REQUIRED_SKILL_DESCRIPTION!r}")
    if not is_quoted_frontmatter_scalar(skill_text, "description"):
        errors.append("SKILL.md description must be double-quoted")
    metadata = parse_openai_metadata((root / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    for path, expected in REQUIRED_METADATA.items():
        actual = metadata.get(path)
        if actual != expected:
            errors.append(f"metadata {'.'.join(path)} must be {expected!r}")
    return errors


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Parse the simple top-level SKILL.md frontmatter shape."""

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}
    metadata: dict[str, str] = {}
    for raw_line in lines[1:]:
        if raw_line == "---":
            break
        if raw_line.startswith(" ") or ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        metadata[key.strip()] = normalize_scalar(value)
    return metadata


def is_quoted_frontmatter_scalar(text: str, key: str) -> bool:
    """Return whether one top-level frontmatter scalar is double-quoted."""

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return False
    prefix = f"{key}:"
    for raw_line in lines[1:]:
        if raw_line == "---":
            return False
        stripped = raw_line.strip()
        if stripped.startswith(prefix):
            value = stripped.removeprefix(prefix).strip()
            return len(value) >= 2 and value[0] == '"' and value[-1] == '"'
    return False


def missing_required_files(root: Path) -> list[str]:
    """Return missing required package file errors."""

    return [f"missing required file: {relative}" for relative in REQUIRED_FILES if not (root / relative).is_file()]


def forbidden_artifact_errors(root: Path) -> list[str]:
    """Return forbidden generated artifact and nested project errors."""

    return [
        f"forbidden skill package artifact: {path.relative_to(root)}"
        for path in sorted(root.rglob("*"))
        if is_forbidden_artifact(path)
    ]


def is_forbidden_artifact(path: Path) -> bool:
    """Return whether a path is forbidden inside this skill package."""

    return not is_finder_metadata(path) and (path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES)


def is_finder_metadata(path: Path) -> bool:
    """Ignore only regular Finder metadata files, never links or directories."""

    return path.name == ".DS_Store" and not path.is_symlink() and path.is_file()


def parse_openai_metadata(text: str) -> dict[tuple[str, str], str]:
    """Parse the simple two-level agents/openai.yaml metadata shape."""

    metadata: dict[tuple[str, str], str] = {}
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            section = stripped[:-1]
            continue
        if section and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            metadata[(section, key.strip())] = normalize_scalar(value)
    return metadata


def normalize_scalar(value: str) -> str:
    """Normalize one simple YAML scalar value."""

    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    return stripped


def compare_skill_packages(*, source: Path, target: Path) -> list[str]:
    """Return source/live file and executable drift, excluding Finder metadata."""

    errors: list[str] = []
    source_files = relative_files(source)
    target_files = relative_files(target)
    for relative in sorted(set(source_files) - set(target_files)):
        errors.append(f"installed skill missing file: {relative}")
    for relative in sorted(set(target_files) - set(source_files)):
        errors.append(f"installed skill has unexpected file: {relative}")
    for relative in sorted(set(source_files) & set(target_files)):
        source_path = source_files[relative]
        target_path = target_files[relative]
        if source_path.read_bytes() != target_path.read_bytes():
            errors.append(f"installed skill file differs: {relative}")
        if executable_bit(source_path) != executable_bit(target_path):
            errors.append(f"installed skill file mode differs: {relative}")
    return errors


def relative_files(root: Path) -> dict[str, Path]:
    """Return package files by relative path, excluding regular .DS_Store files."""

    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*"))
        if not is_finder_metadata(path) and path.is_file()
    }


def executable_bit(path: Path) -> bool:
    """Return whether a file has any executable bit set."""

    return bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def sync_skill_package(*, source: Path, target: Path) -> None:
    """Replace the installed package without copying source Finder metadata."""

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, copy_function=shutil.copy2, ignore=finder_metadata_names)


def finder_metadata_names(directory: str, names: list[str]) -> list[str]:
    """Select only regular .DS_Store files for copytree to omit."""

    return [name for name in names if is_finder_metadata(Path(directory) / name)]


def emit_errors(title: str, errors: list[str]) -> None:
    """Write validation errors to stderr."""

    _ = sys.stderr.write(f"{title}:\n")
    for error in errors:
        _ = sys.stderr.write(f"- {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
