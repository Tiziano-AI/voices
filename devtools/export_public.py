#!/usr/bin/env python3
"""Export an allowlisted committed Voices tree, never history or local state."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "devtools/public-source-files.txt"
PLUGIN_FILES = frozenset(("plugin.json", ".claude-plugin/plugin.json", "LICENSE", "NOTICE.md", "PLUGIN.md"))
SKILL_PREFIX = "skills/voices-local-studio/"
REVIEWED_VISUAL_ASSETS = frozenset((SKILL_PREFIX + "assets/voices.svg", SKILL_PREFIX + "assets/voices.png"))
SKILL_DEVELOPMENT_FILES = frozenset(("basedpyrightconfig.json", "scripts/check_generated_artifacts.py"))
FORBIDDEN_PARTS = frozenset(
    (".git", ".tmp", ".cdx-continue", ".venv", "node_modules", "outputs", "storyshots", "test-results", "__pycache__")
)
MEDIA_SUFFIXES = frozenset((".wav", ".mp3", ".mp4", ".mov", ".png", ".jpg", ".jpeg", ".webp", ".safetensors", ".bin"))


def git_bytes(repo: Path, *arguments: str) -> bytes:
    """Read one exact Git object without checking out or changing the repository."""
    return subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True).stdout


def committed_files(repo: Path, revision: str) -> dict[str, str]:
    """Read regular tracked blob identities from one resolved commit."""
    files: dict[str, str] = {}
    for entry in git_bytes(repo, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode("ascii").split()
        path = name.decode("utf-8")
        if kind == "blob" and mode in ("100644", "100755"):
            files[path] = blob
    return files


def admitted_paths(text: str) -> list[str]:
    """Parse a closed, reviewed path inventory and reject unsafe additions."""
    paths = [line for line in text.splitlines() if line and not line.startswith("#")]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("public source inventory must be nonempty and contain no duplicates")
    for name in paths:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != name or "\\" in name:
            raise ValueError(f"unsafe public source path: {name}")
        if any(part in FORBIDDEN_PARTS for part in path.parts) or name.startswith("docs/releases/"):
            raise ValueError(f"local state/history cannot be exported: {name}")
        if path.suffix.lower() in MEDIA_SUFFIXES and name not in REVIEWED_VISUAL_ASSETS:
            raise ValueError(f"media/model assets are not admitted: {name}")
        if path.suffix.lower() == ".svg" and name not in REVIEWED_VISUAL_ASSETS:
            raise ValueError(f"unreviewed visual asset: {name}")
    return sorted(paths)


def plugin_path(name: str) -> bool:
    """Select the canonical operator payload without development tests or config."""
    if name in PLUGIN_FILES:
        return True
    if not name.startswith(SKILL_PREFIX):
        return False
    relative = name.removeprefix(SKILL_PREFIX)
    return not relative.startswith("tests/") and relative not in SKILL_DEVELOPMENT_FILES


def collect_export(repo: Path, kind: str) -> tuple[str, dict[str, bytes]]:
    """Collect only allowlisted regular blobs from HEAD, not dirty or ignored files."""
    revision = git_bytes(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    files = committed_files(repo, revision)
    manifest_blob = files.get(MANIFEST)
    if manifest_blob is None:
        raise ValueError("commit the public source inventory before exporting")
    inventory = admitted_paths(git_bytes(repo, "cat-file", "blob", manifest_blob).decode("utf-8"))
    missing = sorted(set(inventory) - files.keys())
    if missing:
        raise ValueError(f"inventory members are absent or not regular committed files: {', '.join(missing)}")
    selected = [name for name in inventory if kind == "source" or plugin_path(name)]
    if kind == "plugin" and not PLUGIN_FILES.issubset(selected):
        raise ValueError("plugin export requires both manifests, license, notices and package guide")
    return revision, {name: git_bytes(repo, "cat-file", "blob", files[name]) for name in selected}


def write_archive(output: Path, members: dict[str, bytes]) -> None:
    """Create a byte-reproducible ZIP without links, variable dates or extra files."""
    with output.open("xb") as destination:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)


def main() -> int:
    """Export or inspect an exact committed candidate; never install or publish it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("source", "plugin"), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="new ZIP path; existing paths are refused")
    mode.add_argument("--list", action="store_true", help="print the exact committed membership without writing")
    args = parser.parse_args()
    try:
        revision, members = collect_export(REPO_ROOT, args.kind)
        if args.output is not None:
            write_archive(args.output, members)
        print(json.dumps({"commit": revision, "kind": args.kind, "files": sorted(members)}))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"voices export: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
