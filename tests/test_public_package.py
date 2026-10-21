"""Closed public export and native skills-only package contracts."""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from devtools import export_public


def commit_fixture(repo: Path, files: dict[str, str | bytes]) -> None:
    """Make one private local commit without relying on user Git configuration."""
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )


def test_export_reads_only_inventoried_committed_regular_blobs(tmp_path: Path) -> None:
    """Dirty files, history, secrets and links cannot hitchhike into a source ZIP."""
    repo = tmp_path / "repo"
    logo_path = "skills/voices-local-studio/assets/voices.png"
    logo_bytes = b"\x89PNG\r\n\x1a\ncommitted-logo"
    commit_fixture(
        repo,
        {
            export_public.MANIFEST: f"README.md\nsrc/tool.py\n{logo_path}\n",
            "README.md": "accepted\n",
            "src/tool.py": "print('source')\n",
            logo_path: logo_bytes,
            "private.txt": "not admitted\n",
            "docs/releases/private.md": "historical local report\n",
        },
    )
    (repo / "README.md").write_text("dirty working copy\n")
    (repo / logo_path).write_bytes(b"dirty working logo")
    (repo / "untracked.wav").write_bytes(b"private audio")
    revision, members = export_public.collect_export(repo, "source")
    assert len(revision) == 40
    assert members == {"README.md": b"accepted\n", "src/tool.py": b"print('source')\n", logo_path: logo_bytes}
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    for output in (first, second):
        export_public.write_archive(output, members)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == sorted(members)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    with pytest.raises(FileExistsError):
        export_public.write_archive(first, members)


@pytest.mark.parametrize(
    "name",
    [
        "../secret",
        "/absolute",
        "a//b",
        "a\\b",
        ".git/config",
        ".tmp/report.json",
        "docs/releases/report.md",
        "clip.wav",
        "model.safetensors",
        "photo.png",
        "skills/voices-local-studio/assets/unreviewed.png",
        "skills/another-skill/assets/voices.png",
        "unreviewed.svg",
    ],
)
def test_inventory_rejects_unsafe_state_history_or_unreviewed_assets(name: str) -> None:
    with pytest.raises(ValueError):
        export_public.admitted_paths(name + "\n")


def test_inventory_rejects_duplicate_members() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        export_public.admitted_paths("README.md\nREADME.md\n")


def test_plugin_export_uses_its_guide_as_the_only_readme(tmp_path: Path) -> None:
    """A standalone plugin explains setup without linking to excluded developer files."""
    repo = tmp_path / "repo"
    files = {
        "plugin.json": "{}\n",
        ".claude-plugin/plugin.json": "{}\n",
        "LICENSE": "MIT\n",
        "NOTICE.md": "Distribution notices.\n",
        "PLUGIN.md": "# Agent plugin\n\n[Notices](NOTICE.md).\n",
        "README.md": "# Developer source\n\n[Build](devtools/README.md).\n",
    }
    commit_fixture(repo, {**files, export_public.MANIFEST: "\n".join(files) + "\n"})
    _, plugin = export_public.collect_export(repo, "plugin")
    _, source = export_public.collect_export(repo, "source")
    assert plugin["README.md"] == files["PLUGIN.md"].encode()
    assert "PLUGIN.md" not in plugin
    assert source["README.md"] == files["README.md"].encode()
    assert source["PLUGIN.md"] == files["PLUGIN.md"].encode()


def test_inventory_cannot_admit_committed_links(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    commit_fixture(repo, {export_public.MANIFEST: "alias.py\n", "owner.py": "original\n"})
    (repo / "alias.py").symlink_to("owner.py")
    subprocess.run(["git", "-C", str(repo), "add", "alias.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "link",
        ],
        check=True,
    )
    with pytest.raises(ValueError, match="not regular committed files"):
        export_public.collect_export(repo, "source")


def test_working_inventory_is_closed_and_payload_has_no_external_local_links() -> None:
    root = export_public.REPO_ROOT
    inventory = export_public.admitted_paths((root / export_public.MANIFEST).read_text())
    assert set(export_public.PLUGIN_FILES).issubset(inventory)
    assert export_public.REVIEWED_VISUAL_ASSETS.issubset(inventory)
    assert export_public.MANIFEST in inventory
    for name in inventory:
        assert (root / name).is_file() and not (root / name).is_symlink(), name
    payload = [name for name in inventory if export_public.plugin_path(name)]
    for name in payload:
        content = (root / name).read_bytes()
        assert b"/Users/" not in content, name
        if name.endswith(".md"):
            text = content.decode("utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                linked = ((root / name).parent / target.split("#", 1)[0]).resolve()
                assert linked.relative_to(root).as_posix() in payload, (name, target)
    assert not any("/tests/" in name or name.endswith("basedpyrightconfig.json") for name in payload)


def test_upstream_configuration_fixture_keeps_its_source_only_notices() -> None:
    root = export_public.REPO_ROOT
    inventory = export_public.admitted_paths((root / export_public.MANIFEST).read_text())
    required = {
        "tests/fixtures/qwen3_forced_aligner_53c8c0e_config.json",
        "tests/fixtures/NOTICE.md",
        "tests/fixtures/LICENSE.Apache-2.0",
    }
    assert required.issubset(inventory)
    assert not any(export_public.plugin_path(name) for name in required)
    notice = (root / "tests/fixtures/NOTICE.md").read_text()
    assert "53c8c0e46733eec430e4b53dd6471d0e5dee45f8" in notice
    assert "one final newline was appended" in notice
    assert "Apache License" in (root / "tests/fixtures/LICENSE.Apache-2.0").read_text()


def test_native_manifests_discover_one_skill_without_automatic_effects() -> None:
    root = export_public.REPO_ROOT
    portable = json.loads((root / "plugin.json").read_text())
    claude = json.loads((root / ".claude-plugin/plugin.json").read_text())
    for key in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
        assert portable[key] == claude[key]
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert portable["name"] == "voices"
    assert portable["license"] == "MIT"
    assert claude["icon"] == "./skills/voices-local-studio/assets/voices.png"
    assert sorted(path.name for path in (root / "skills").iterdir()) == ["voices-local-studio"]
    assert not any(key in portable or key in claude for key in ("hooks", "mcpServers", "settings", "commands"))
    extension = portable["extensions"]["com.openai"]
    assert set(extension) == {"requires_local_executor", "interface"}
    assert extension["requires_local_executor"] is True
    for key in ("composerIcon", "logo"):
        assert (root / extension["interface"][key]).is_file()
    assert not any((root / name).exists() for name in ("mcp.json", ".mcp.json", "hooks/hooks.json"))
