import json
from pathlib import Path
from threading import Event, Thread

import numpy as np
import pytest
from pydantic import ValidationError

from voices import config
from voices.domain.contracts import OutputDraft, OutputRecord
from voices.domain.errors import InvalidInputError, InvalidOutputEntryError
from voices.runtime_identity import RuntimeIdentity
from voices.store.output_store import list_output_artifacts, output_artifact_for_name, save_rendered_output


def _make_audio() -> np.ndarray:
    return np.random.default_rng(42).uniform(-0.5, 0.5, 2400).astype(np.float32)


def _draft() -> OutputDraft:
    return OutputDraft(
        voice_id="test_voice",
        created_at="2026-04-08T12:00:00Z",
        language="English",
        base_model_id=config.BASE_MODEL,
        base_model_revision=config.BASE_MODEL_REVISION,
        runtime=RuntimeIdentity(
            python="test-python",
            executable="/test/python",
            platform="test-platform",
            voices_version="test-version",
            source_sha256="b" * 64,
            packages={"mlx-audio": "test-version"},
        ),
        text="Hello world.",
        reference_voice_id="test_voice",
        reference_sha256="a" * 64,
        reference_text_sha256="c" * 64,
    )


def _record_payload(output_audio: str) -> dict[str, object]:
    return {
        "schema_version": 2,
        "voice_id": "test_voice",
        "created_at": "2026-04-08T12:00:00Z",
        "language": "English",
        "base_model_id": config.BASE_MODEL,
        "text": "Hello world.",
        "output_audio": output_audio,
        "reference_voice_id": "test_voice",
        "reference_sha256": "a" * 64,
    }


def test_save_output(tmp_path):
    wav_path = save_rendered_output(tmp_path / "outputs", _draft(), _make_audio(), 24000)

    sidecar = wav_path.with_suffix(".json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert wav_path.exists()
    assert sidecar.exists()
    assert payload["schema_version"] == 2
    assert payload["voice_id"] == "test_voice"
    assert payload["reference_voice_id"] == "test_voice"
    assert payload["reference_text_sha256"] == "c" * 64
    assert payload["output_audio"] == wav_path.name
    assert "source_reference_audio" not in payload


def test_output_record_rejects_path_like_audio_name():
    with pytest.raises(ValidationError, match="basename"):
        OutputRecord.model_validate(_record_payload("../evil.wav"))


def test_output_listing_rejects_noncanonical_sidecar_name(tmp_path):
    target_dir = tmp_path / "outputs" / "test_voice"
    target_dir.mkdir(parents=True)
    wav_name = "20260408T120000Z__hello-world.wav"
    (target_dir / wav_name).write_bytes(b"RIFF")
    (target_dir / "not-canonical.json").write_text(json.dumps(_record_payload(wav_name)), encoding="utf-8")

    with pytest.raises(InvalidOutputEntryError, match="invalid entries"):
        list_output_artifacts(tmp_path / "outputs", "test_voice")


def test_output_sidecar_name_must_match_output_audio(tmp_path):
    target_dir = tmp_path / "outputs" / "test_voice"
    target_dir.mkdir(parents=True)
    wav_name = "20260408T120000Z__other.wav"
    (target_dir / wav_name).write_bytes(b"RIFF")
    sidecar = target_dir / "20260408T120000Z__hello-world.json"
    sidecar.write_text(json.dumps(_record_payload(wav_name)), encoding="utf-8")

    with pytest.raises(InvalidOutputEntryError, match="does not match output_audio"):
        output_artifact_for_name(tmp_path / "outputs", "test_voice", sidecar.name)


def test_save_output_rejects_symlinked_output_directory(tmp_path):
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (out_dir / "test_voice").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(InvalidInputError, match="output voice id"):
        save_rendered_output(out_dir, _draft(), _make_audio(), 24000)


def test_save_output_rejects_symlinked_output_root(tmp_path):
    real_root = tmp_path / "real-outputs"
    real_root.mkdir()
    out_dir = tmp_path / "outputs"
    out_dir.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(InvalidInputError, match="Output root"):
        save_rendered_output(out_dir, _draft(), _make_audio(), 24000)


def test_save_output_rejects_non_directory_output_root(tmp_path):
    out_dir = tmp_path / "outputs"
    out_dir.write_text("not a directory", encoding="utf-8")

    with pytest.raises(InvalidInputError, match="Output root must be a directory"):
        save_rendered_output(out_dir, _draft(), _make_audio(), 24000)


def test_save_output_rejects_non_directory_output_voice_path(tmp_path):
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    (out_dir / "test_voice").write_text("not a directory", encoding="utf-8")

    with pytest.raises(InvalidInputError, match="path must be a directory"):
        save_rendered_output(out_dir, _draft(), _make_audio(), 24000)


def test_save_output_rejects_broken_symlink_artifact_name(tmp_path, monkeypatch):
    import voices.store.output_store as output_store

    out_dir = tmp_path / "outputs"
    target_dir = out_dir / "test_voice"
    target_dir.mkdir(parents=True)
    (target_dir / "20260408T120000Z__hello-world.wav").symlink_to(tmp_path / "missing.wav")
    monkeypatch.setattr(output_store, "utc_now_compact", lambda: "20260408T120000Z")

    with pytest.raises(InvalidInputError, match="Output artifact path"):
        save_rendered_output(out_dir, _draft(), _make_audio(), 24000)


def test_save_output_treats_orphan_sidecar_as_collision(tmp_path, monkeypatch):
    import voices.store.output_store as output_store

    out_dir = tmp_path / "outputs"
    target_dir = out_dir / "test_voice"
    target_dir.mkdir(parents=True)
    orphan_sidecar = target_dir / "20260408T120000Z__hello-world.json"
    orphan_sidecar.write_text('{"old": true}\n', encoding="utf-8")
    monkeypatch.setattr(output_store, "utc_now_compact", lambda: "20260408T120000Z")

    wav_path = save_rendered_output(out_dir, _draft(), _make_audio(), 24000)

    assert wav_path.name == "20260408T120000Z__hello-world-2.wav"
    assert json.loads(orphan_sidecar.read_text(encoding="utf-8")) == {"old": True}


def test_concurrent_render_publication_uses_unique_suffixes(tmp_path, monkeypatch):
    import voices.store.output_store as output_store

    out_dir = tmp_path / "outputs"
    draft = _draft()
    first_write_started = Event()
    release_first_write = Event()
    first_write_blocked = False
    original_write_wav = output_store.write_wav
    results: list[Path] = []
    failures: list[Exception] = []

    def blocked_write_wav(path: Path, audio_data: np.ndarray, sample_rate: int) -> None:
        nonlocal first_write_blocked
        if not first_write_blocked:
            first_write_blocked = True
            first_write_started.set()
            assert release_first_write.wait(5)
        original_write_wav(path, audio_data, sample_rate)

    def render() -> None:
        try:
            results.append(save_rendered_output(out_dir, draft, _make_audio(), 24000))
        except Exception as error:  # pragma: no cover - surfaced below
            failures.append(error)

    monkeypatch.setattr(output_store, "utc_now_compact", lambda: "20260408T120000Z")
    monkeypatch.setattr(output_store, "write_wav", blocked_write_wav)

    first_thread = Thread(target=render)
    first_thread.start()
    assert first_write_started.wait(5)
    second_thread = Thread(target=render)
    second_thread.start()
    release_first_write.set()
    first_thread.join()
    second_thread.join()

    assert failures == []
    assert sorted(path.name for path in results) == [
        "20260408T120000Z__hello-world-2.wav",
        "20260408T120000Z__hello-world.wav",
    ]
    assert all(path.with_suffix(".json").exists() for path in results)
