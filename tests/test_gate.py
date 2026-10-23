"""Repository gate and skill sync contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from devtools import check_file_size, check_skill, gate, sync_skill


def write_minimal_skill(root: Path) -> None:
    """Write a minimal structurally valid voices skill package."""

    for relative in sync_skill.REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    (root / "SKILL.md").write_text(
        f'---\nname: voices-local-studio\ndescription: "{sync_skill.REQUIRED_SKILL_DESCRIPTION}"\n---\n',
        encoding="utf-8",
    )
    (root / "agents" / "openai.yaml").write_text(
        "interface:\n"
        '  display_name: "Voices Local Studio"\n'
        f'  short_description: "{sync_skill.REQUIRED_SHORT_DESCRIPTION}"\n'
        f'  default_prompt: "{sync_skill.REQUIRED_DEFAULT_PROMPT}"\n'
        '  icon_small: "./assets/voices.svg"\n'
        '  icon_large: "./assets/voices.png"\n'
        '  brand_color: "#953D4E"\n'
        "policy:\n"
        "  allow_implicit_invocation: true\n",
        encoding="utf-8",
    )


def test_gate_validates_source_without_requiring_a_global_skill() -> None:
    """A fresh checkout can validate without installing or replacing an operator skill."""

    assert gate.COMMANDS[:2] == [
        ["uv", "run", "python", "devtools/sync_skill.py", "--validate-source"],
        ["uv", "run", "python", "devtools/check_skill.py"],
    ]


def test_skill_tools_share_the_native_canonical_root() -> None:
    """Native discovery and standalone projection consume one source package."""
    expected = gate.REPO_ROOT / "skills" / "voices-local-studio"
    assert sync_skill.SOURCE_ROOT == check_skill.SKILL_ROOT == expected
    assert not (gate.REPO_ROOT / "config" / "skills" / "voices-local-studio").exists()


def test_source_validation_does_not_access_an_installed_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Source-only validation leaves a missing or unrelated installed package alone."""
    source, target = tmp_path / "source", tmp_path / "not-installed"
    write_minimal_skill(source)
    monkeypatch.setattr(sync_skill, "SOURCE_ROOT", source)
    monkeypatch.setattr(sync_skill, "TARGET_ROOT", target)
    monkeypatch.setattr("sys.argv", ["sync_skill.py", "--validate-source"])
    assert sync_skill.main() == 0
    assert not target.exists()
    assert capsys.readouterr().out == "source skill package validation passed\n"


def test_skill_checks_use_repository_locked_tools() -> None:
    """Avoid resolving a different unpinned toolchain in a personal shared environment."""
    prefix = ["uv", "run", "--locked", "--project", str(check_skill.REPO_ROOT)]
    commands = check_skill.skill_check_commands()
    assert all(command[: len(prefix)] == prefix for command in commands if "basedpyright" not in command)
    assert next(command for command in commands if "basedpyright" in command) == [
        "pnpm",
        "--dir",
        str(check_skill.REPO_ROOT / "web"),
        "exec",
        "basedpyright",
        "--project",
        str(check_skill.SKILL_ROOT / "basedpyrightconfig.json"),
        "--level",
        "error",
    ]
    assert check_skill.skill_env()["PYTHONPATH"] == str(check_skill.SKILL_ROOT / "scripts")


def test_file_size_guard_excludes_local_continuation_records() -> None:
    """Keep local continuation ledgers outside the repository-owned source set."""

    continuation = check_file_size.REPO_ROOT / ".cdx-continue" / "latest.md"

    assert not check_file_size.is_checked_file(continuation)


def test_validate_skill_package_rejects_nested_project_files(tmp_path: Path) -> None:
    """Prevent product-shaped Python project files inside the skill package."""

    write_minimal_skill(tmp_path)
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    errors = sync_skill.validate_skill_package(tmp_path)

    assert "forbidden skill package artifact: uv.lock" in errors


def test_validate_skill_package_rejects_default_prompt_drift(tmp_path: Path) -> None:
    """Keep invocation metadata aligned with the voices skill boundary."""

    write_minimal_skill(tmp_path)
    metadata_path = tmp_path / "agents" / "openai.yaml"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace(
            sync_skill.REQUIRED_DEFAULT_PROMPT,
            "Give generic voice advice.",
        ),
        encoding="utf-8",
    )

    errors = sync_skill.validate_skill_package(tmp_path)

    assert "metadata interface.default_prompt must be" in "\n".join(errors)


def test_validate_skill_package_rejects_unquoted_skill_description(tmp_path: Path) -> None:
    """Prevent loader-fragile unquoted free-text frontmatter."""

    write_minimal_skill(tmp_path)
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(
        skill_path.read_text(encoding="utf-8").replace(
            f'description: "{sync_skill.REQUIRED_SKILL_DESCRIPTION}"',
            f"description: {sync_skill.REQUIRED_SKILL_DESCRIPTION}",
        ),
        encoding="utf-8",
    )

    errors = sync_skill.validate_skill_package(tmp_path)

    assert "SKILL.md description must be double-quoted" in errors


def test_compare_skill_packages_detects_live_drift(tmp_path: Path) -> None:
    """Ensure sync check catches source/live content drift."""

    source = tmp_path / "source"
    target = tmp_path / "target"
    write_minimal_skill(source)
    write_minimal_skill(target)
    (target / "SKILL.md").write_text("changed\n", encoding="utf-8")

    errors = sync_skill.compare_skill_packages(source=source, target=target)

    assert "installed skill file differs: SKILL.md" in errors


@pytest.mark.parametrize("placement", ["source", "target", "both"])
@pytest.mark.parametrize("relative", [".DS_Store", "references/.DS_Store", "scripts/nested/.DS_Store"])
def test_check_ignores_finder_file_presence_bytes_and_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], placement: str, relative: str
) -> None:
    """Finder files cannot invalidate an otherwise identical source/live package."""

    source, target = tmp_path / "source", tmp_path / "target"
    for root, label, mode in [(source, "source", 0o644), (target, "target", 0o755)]:
        write_minimal_skill(root)
        if placement in (label, "both"):
            metadata = root / relative
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_bytes(label.encode())
            metadata.chmod(mode)
        assert sync_skill.validate_skill_package(root) == []

    assert sync_skill.compare_skill_packages(source=source, target=target) == []
    monkeypatch.setattr(sync_skill, "SOURCE_ROOT", source)
    monkeypatch.setattr(sync_skill, "TARGET_ROOT", target)
    monkeypatch.setattr("sys.argv", ["sync_skill.py", "--check"])

    assert sync_skill.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "skill package sync check passed\n"
    assert captured.err == ""


def test_sync_excludes_only_finder_files_and_preserves_package_content(tmp_path: Path) -> None:
    """Copy meaningful files and modes, including content in a Finder-named directory."""

    source, target = tmp_path / "source", tmp_path / "target"
    write_minimal_skill(source)
    write_minimal_skill(target)
    for relative in [".DS_Store", "scripts/.DS_Store", "references/nested/.DS_Store"]:
        metadata = source / relative
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_bytes(b"Finder metadata")
        metadata.chmod(0o755)
    (target / ".DS_Store").write_bytes(b"old Finder metadata")
    executable = source / "scripts/voice_prompt_workbench.py"
    executable.write_bytes(b"#!/usr/bin/env python3\nprint('meaningful')\n")
    executable.chmod(0o751)
    ordinary = source / "references/local-product-contract.md"
    ordinary.chmod(0o640)
    nested_content = source / "assets/.DS_Store/notes.txt"
    nested_content.parent.mkdir(parents=True)
    nested_content.write_bytes(b"This is package content, not a Finder file.")

    sync_skill.sync_skill_package(source=source, target=target)

    assert not any(path.name == ".DS_Store" and path.is_file() for path in target.rglob("*"))
    assert (source / ".DS_Store").read_bytes() == b"Finder metadata"
    assert (target / "assets/.DS_Store/notes.txt").read_bytes() == nested_content.read_bytes()
    assert (target / "scripts/voice_prompt_workbench.py").read_bytes() == executable.read_bytes()
    assert (target / "scripts/voice_prompt_workbench.py").stat().st_mode & 0o777 == 0o751
    assert (target / "references/local-product-contract.md").stat().st_mode & 0o777 == 0o640
    assert sync_skill.validate_skill_package(target) == ["forbidden skill package artifact: assets/.DS_Store"]
    assert sync_skill.compare_skill_packages(source=source, target=target) == []


@pytest.mark.parametrize(
    ("drift", "expected"),
    [
        ("missing", "installed skill missing file: notes.txt"),
        ("extra", "installed skill has unexpected file: extra.txt"),
        ("content", "installed skill file differs: notes.txt"),
        ("mode", "installed skill file mode differs: notes.txt"),
    ],
)
def test_check_still_rejects_meaningful_drift_with_finder_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], drift: str, expected: str
) -> None:
    """The metadata exception does not disable any source/live drift check."""

    source, target = tmp_path / "source", tmp_path / "target"
    for root in (source, target):
        write_minimal_skill(root)
        (root / "notes.txt").write_bytes(b"original")
        (root / "notes.txt").chmod(0o644)
        (root / ".DS_Store").write_bytes(root.name.encode())
    if drift == "missing":
        (target / "notes.txt").unlink()
    elif drift == "extra":
        (target / "extra.txt").write_bytes(b"unexpected")
    elif drift == "content":
        (target / "notes.txt").write_bytes(b"changed")
    else:
        (target / "notes.txt").chmod(0o744)

    assert sync_skill.compare_skill_packages(source=source, target=target) == [expected]
    monkeypatch.setattr(sync_skill, "SOURCE_ROOT", source)
    monkeypatch.setattr(sync_skill, "TARGET_ROOT", target)
    monkeypatch.setattr("sys.argv", ["sync_skill.py", "--check"])
    assert sync_skill.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert expected in captured.err


@pytest.mark.parametrize(
    "relative",
    [
        "nested/.pytest_cache",
        "nested/.ruff_cache",
        "nested/.venv",
        "nested/__pycache__",
        "nested/pyproject.toml",
        "nested/uv.lock",
        "nested/compiled.pyc",
        "nested/compiled.pyo",
        "nested/.DS_Store.pyc",
        ".DS_Store/uv.lock",
    ],
)
def test_finder_exception_keeps_other_artifacts_forbidden(tmp_path: Path, relative: str) -> None:
    """Exclude only the exact metadata file, not similarly named files or subtrees."""

    write_minimal_skill(tmp_path)
    artifact = tmp_path / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if artifact.name in {".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}:
        artifact.mkdir()
    else:
        artifact.write_bytes(b"forbidden")

    assert f"forbidden skill package artifact: {relative}" in sync_skill.validate_skill_package(tmp_path)


@pytest.mark.parametrize("destination_exists", [True, False])
def test_finder_named_symlinks_remain_forbidden(tmp_path: Path, destination_exists: bool) -> None:
    """Finder exclusions admit regular files only, not links or broken links."""

    write_minimal_skill(tmp_path)
    destination = tmp_path / "references/linked.txt"
    if destination_exists:
        destination.write_bytes(b"not metadata")
    (tmp_path / ".DS_Store").symlink_to(destination)

    assert "forbidden skill package artifact: .DS_Store" in sync_skill.validate_skill_package(tmp_path)
