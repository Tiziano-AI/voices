import json
from pathlib import Path

import pytest
from voice_workbench.audit import audit_json_spec_path, audit_jsonl_path, audit_prose_item
from voice_workbench.compose import compose_instruct
from voice_workbench.contracts import AuditItem, VoiceProfile


def _diagnostic_codes(item: AuditItem) -> set[str]:
    return {diagnostic.code for diagnostic in item.diagnostics}


def test_jsonl_rows_require_seed_text_when_row_text_is_missing(tmp_path: Path):
    prompt_pack = tmp_path / "pack.jsonl"
    prompt_pack.write_text('{"id":"voice_01","instruct":"Warm narrator"}\n', encoding="utf-8")

    missing_text_items = audit_jsonl_path(prompt_pack, None, strict_imitation=False)
    default_text_items = audit_jsonl_path(prompt_pack, "Control is not the absence of feeling.", strict_imitation=False)

    assert "missing_seed_text" in _diagnostic_codes(missing_text_items[0])
    assert "missing_seed_text" not in _diagnostic_codes(default_text_items[0])


def test_structured_spec_requires_seed_text_when_text_is_missing(tmp_path: Path):
    structured_spec = tmp_path / "spec.json"
    structured_spec.write_text(
        json.dumps(
            {
                "id": "voice_01",
                "name": "Voice 01",
                "language": "English",
                "text": "",
                "voice": {
                    "pace": "Measured",
                    "purpose": "Morning Radio",
                    "characteristics": ["bright"],
                },
            }
        ),
        encoding="utf-8",
    )

    items = audit_json_spec_path(structured_spec, None, strict_imitation=False)

    assert "missing_seed_text" in _diagnostic_codes(items[0])


def test_structured_spec_checks_full_voice_for_imitation_risk(tmp_path: Path):
    structured_spec = tmp_path / "spec.json"
    structured_spec.write_text(
        json.dumps(
            {
                "id": "voice_01",
                "language": "English",
                "text": "A short calibration line.",
                "voice": {
                    "pace": "Measured",
                    "purpose": "documentary narration",
                    "archetype": "Morgan Freeman-style narrator",
                },
            }
        ),
        encoding="utf-8",
    )

    items = audit_json_spec_path(structured_spec, None, strict_imitation=True)

    assert "imitation_risk" in _diagnostic_codes(items[0])


def test_capitalized_purpose_does_not_trigger_imitation_risk():
    prompt = compose_instruct(
        VoiceProfile(
            pace="Measured",
            diction="clean",
            characteristics=("bright",),
            purpose="Morning Radio",
        ),
        "balanced-literary",
    )

    audit_item = audit_prose_item("inline", prompt, strict_imitation=True)
    imitation_item = audit_prose_item("inline", "Sound like Morgan Freeman.", strict_imitation=True)

    assert "imitation_risk" not in _diagnostic_codes(audit_item)
    assert "imitation_risk" in _diagnostic_codes(imitation_item)


def test_named_style_suffix_triggers_imitation_risk():
    audit_item = audit_prose_item(
        "inline",
        "Morgan Freeman-style prestige documentary narrator with calm baritone.",
        strict_imitation=True,
    )

    assert "imitation_risk" in _diagnostic_codes(audit_item)


def test_generated_artifact_guard_reports_nested_project_files(tmp_path: Path):
    from check_generated_artifacts import generated_artifacts

    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    assert generated_artifacts(tmp_path) == ["pyproject.toml", "uv.lock"]


def test_generated_artifact_guard_ignores_exact_finder_files(tmp_path: Path):
    from check_generated_artifacts import generated_artifacts

    for relative in [".DS_Store", "scripts/.DS_Store", "assets/nested/.DS_Store"]:
        metadata = tmp_path / relative
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_bytes(b"Finder metadata")
        metadata.chmod(0o755)

    assert generated_artifacts(tmp_path) == []


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
def test_generated_artifact_guard_keeps_other_artifacts_forbidden(tmp_path: Path, relative: str):
    from check_generated_artifacts import generated_artifacts

    artifact = tmp_path / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if artifact.name in {".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}:
        artifact.mkdir()
    else:
        artifact.write_bytes(b"forbidden")

    assert relative in generated_artifacts(tmp_path)


@pytest.mark.parametrize("destination_exists", [True, False])
def test_generated_artifact_guard_rejects_finder_named_symlinks(tmp_path: Path, destination_exists: bool):
    from check_generated_artifacts import generated_artifacts

    destination = tmp_path / "linked.txt"
    if destination_exists:
        destination.write_bytes(b"not metadata")
    (tmp_path / ".DS_Store").symlink_to(destination)

    assert generated_artifacts(tmp_path) == [".DS_Store"]
