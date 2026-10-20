import json
import os
from threading import Barrier, Thread
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import make_clone_draft, make_design_draft
from pydantic import ValidationError

from voices import config
from voices.domain.contracts import VoiceRecord
from voices.domain.errors import (
    InvalidInputError,
    InvalidVoiceEntryError,
    LibraryIntegrityError,
    VoiceAlreadyExistsError,
    VoiceNotFoundError,
)
from voices.store.library_store import (
    delete_voice_record,
    list_voice_records,
    load_voice_record,
    save_voice_record,
)


def _make_audio() -> np.ndarray:
    return np.random.default_rng(42).uniform(-0.5, 0.5, 2400).astype(np.float32)


def test_save_and_load_voice(tmp_path):
    lib = tmp_path / "voices"
    draft = make_design_draft()
    save_voice_record(lib, draft, _make_audio(), 24000)

    loaded = load_voice_record(lib, "test_voice")
    assert loaded.id == "test_voice"
    assert loaded.reference_sha256 != ""
    assert loaded.source.kind == "design"
    assert (lib / "test_voice" / "reference.wav").exists()
    assert (lib / "test_voice" / "reference.txt").exists()
    assert (lib / "test_voice" / "voice.json").exists()


def test_save_clone_voice_persists_clone_source(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_clone_draft("cloned"), _make_audio(), 24000)

    loaded = load_voice_record(lib, "cloned")
    assert loaded.source.kind == "clone"
    payload = json.loads((lib / "cloned" / "voice.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["source"] == {"kind": "clone"}
    assert "reference_audio" not in payload


def test_save_voice_duplicate_raises(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(), _make_audio(), 24000)
    with pytest.raises(VoiceAlreadyExistsError):
        save_voice_record(lib, make_design_draft(), _make_audio(), 24000)


def test_save_voice_overwrite(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(), _make_audio(), 24000)
    save_voice_record(
        lib,
        make_design_draft(reference_text="Updated sample."),
        _make_audio(),
        24000,
        overwrite=True,
    )
    loaded = load_voice_record(lib, "test_voice")
    assert loaded.reference_text == "Updated sample."


def test_save_voice_overwrite_preserves_existing_voice_on_write_failure(tmp_path, monkeypatch):
    import voices.store.library_store as library_store

    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(reference_text="Original sample."), _make_audio(), 24000)

    def fail_write_json(*_args, **_kwargs):
        raise OSError("disk full during metadata write")

    monkeypatch.setattr(library_store, "_write_json", fail_write_json)
    with pytest.raises(OSError, match="disk full"):
        save_voice_record(
            lib,
            make_design_draft(reference_text="Updated sample."),
            _make_audio(),
            24000,
            overwrite=True,
        )

    loaded = load_voice_record(lib, "test_voice")
    assert loaded.reference_text == "Original sample."


def test_load_voice_not_found(tmp_path):
    with pytest.raises(VoiceNotFoundError):
        load_voice_record(tmp_path, "nonexistent")


def test_load_voice_missing_wav(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(), _make_audio(), 24000)
    (lib / "test_voice" / "reference.wav").unlink()
    with pytest.raises(InvalidVoiceEntryError, match="reference.wav"):
        load_voice_record(lib, "test_voice")


def test_load_voice_rejects_symlinked_reference_audio(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(voice_id="symlink_voice"), _make_audio(), 24000)
    reference_audio_path = lib / "symlink_voice" / "reference.wav"
    outside_audio_path = tmp_path / "outside.wav"
    outside_audio_path.write_bytes(reference_audio_path.read_bytes())
    reference_audio_path.unlink()
    reference_audio_path.symlink_to(outside_audio_path)

    with pytest.raises(InvalidVoiceEntryError, match="symlink"):
        load_voice_record(lib, "symlink_voice")


def test_list_voice_records_rejects_symlinked_voice_directory(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("real_voice"), _make_audio(), 24000)
    (lib / "alias_voice").symlink_to(lib / "real_voice", target_is_directory=True)

    with pytest.raises(LibraryIntegrityError, match="alias_voice"):
        list_voice_records(lib)


def test_delete_voice_rejects_symlinked_voice_directory_without_deleting_target(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("real_voice"), _make_audio(), 24000)
    (lib / "alias_voice").symlink_to(lib / "real_voice", target_is_directory=True)

    with pytest.raises(InvalidInputError, match="symlink"):
        delete_voice_record(lib, "alias_voice")

    assert (lib / "real_voice" / "voice.json").exists()


def test_overwrite_rejects_symlinked_voice_directory_without_rewriting_target(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("real_voice", reference_text="Original sample."), _make_audio(), 24000)
    (lib / "alias_voice").symlink_to(lib / "real_voice", target_is_directory=True)

    with pytest.raises(InvalidInputError, match="symlink"):
        save_voice_record(
            lib,
            make_design_draft("alias_voice", reference_text="Updated sample."),
            _make_audio(),
            24000,
            overwrite=True,
        )

    assert load_voice_record(lib, "real_voice").reference_text == "Original sample."


def test_load_voice_transcript_mismatch_raises(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(), _make_audio(), 24000)
    (lib / "test_voice" / "reference.txt").write_text("Different", encoding="utf-8")
    with pytest.raises(InvalidVoiceEntryError, match="transcript disagree"):
        load_voice_record(lib, "test_voice")


def test_list_voices_empty(tmp_path):
    assert list_voice_records(tmp_path / "nope") == []


def test_list_voices_returns_sorted(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(
        lib,
        make_design_draft("alpha", created_at="2026-04-08T10:00:00Z"),
        _make_audio(),
        24000,
    )
    save_voice_record(
        lib,
        make_design_draft("beta", created_at="2026-04-08T09:00:00Z"),
        _make_audio(),
        24000,
    )
    entries = list_voice_records(lib)
    assert [entry.id for entry in entries] == ["beta", "alpha"]


def test_list_voices_tie_breaks_equal_created_at_by_metadata_mtime(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(
        lib,
        make_design_draft("zulu", created_at="2026-04-08T10:00:00Z"),
        _make_audio(),
        24000,
    )
    save_voice_record(
        lib,
        make_design_draft("alpha", created_at="2026-04-08T10:00:00Z"),
        _make_audio(),
        24000,
    )
    os.utime(lib / "zulu" / "voice.json", ns=(100, 100))
    os.utime(lib / "alpha" / "voice.json", ns=(200, 200))

    entries = list_voice_records(lib)

    assert [entry.id for entry in entries] == ["zulu", "alpha"]


def test_list_voices_fail_closed_on_invalid_entry(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("valid_voice"), _make_audio(), 24000)
    broken_dir = lib / "broken_voice"
    broken_dir.mkdir(parents=True)
    (broken_dir / "voice.json").write_text("{}", encoding="utf-8")
    (broken_dir / "reference.txt").write_text("Hello world.", encoding="utf-8")

    with pytest.raises(LibraryIntegrityError, match="broken_voice"):
        list_voice_records(lib)


def test_list_voices_fail_closed_on_non_directory_entry(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("valid_voice"), _make_audio(), 24000)
    (lib / "ghost_voice").write_text("not a directory", encoding="utf-8")

    with pytest.raises(LibraryIntegrityError, match="ghost_voice"):
        list_voice_records(lib)


def test_list_voices_fail_closed_on_malformed_metadata_json(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("broken_voice"), _make_audio(), 24000)
    (lib / "broken_voice" / "voice.json").write_text("{bad json", encoding="utf-8")

    with pytest.raises(LibraryIntegrityError, match="malformed JSON"):
        list_voice_records(lib)


def test_delete_voice(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft(), _make_audio(), 24000)
    delete_voice_record(lib, "test_voice")
    assert not (lib / "test_voice").exists()


def test_delete_voice_not_found(tmp_path):
    with pytest.raises(VoiceNotFoundError):
        delete_voice_record(tmp_path, "nope")


def test_load_voice_rejects_invalid_voice_id(tmp_path):
    with pytest.raises(InvalidInputError, match=r"voice id must match"):
        load_voice_record(tmp_path, "foo/bar")


def test_delete_voice_rejects_invalid_voice_id(tmp_path):
    with pytest.raises(InvalidInputError, match=r"voice id must match"):
        delete_voice_record(tmp_path, ".")


def test_save_voice_rejects_escape_attempt_before_filesystem_touch(tmp_path):
    lib = tmp_path / "voices"
    with pytest.raises(InvalidInputError, match=r"voice id must match"):
        save_voice_record(
            lib,
            SimpleNamespace(id="foo/bar"),
            _make_audio(),
            24000,
        )
    assert not lib.exists()


def test_concurrent_non_overwrite_save_allows_only_one_winner(tmp_path, monkeypatch):
    import voices.store.library_store as library_store

    lib = tmp_path / "voices"
    barrier = Barrier(2)
    original_staging_directory = library_store._staging_directory
    results: list[str] = []

    def staged(parent_directory, *, prefix):
        path = original_staging_directory(parent_directory, prefix=prefix)
        barrier.wait(timeout=5)
        return path

    def save(label: str) -> None:
        try:
            save_voice_record(
                lib,
                make_design_draft("race_voice", reference_text=label),
                _make_audio(),
                24000,
                overwrite=False,
            )
            results.append(f"ok:{label}")
        except VoiceAlreadyExistsError:
            results.append(f"exists:{label}")

    monkeypatch.setattr(library_store, "_staging_directory", staged)
    threads = [Thread(target=save, args=(label,)) for label in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(result.split(":", maxsplit=1)[0] for result in results) == ["exists", "ok"]
    assert load_voice_record(lib, "race_voice").reference_text in {"first", "second"}


def test_voice_record_schema_rejects_empty_design_prompt():
    with pytest.raises(ValidationError, match="voice design prompt"):
        VoiceRecord(
            schema_version=2,
            id="test_voice",
            name="Test Voice",
            created_at="2026-04-08T12:00:00Z",
            language="English",
            base_model_id=config.BASE_MODEL,
            reference_text="Hello world.",
            reference_sha256="a" * 64,
            source={"kind": "design", "model_id": config.VOICE_DESIGN_MODEL, "instruct": " "},
        )


def test_list_voices_reports_invalid_directory_names_as_integrity_errors(tmp_path):
    lib = tmp_path / "voices"
    save_voice_record(lib, make_design_draft("valid_voice"), _make_audio(), 24000)
    invalid_dir = lib / "Bad-ID"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "voice.json").write_text("{}", encoding="utf-8")
    (invalid_dir / "reference.txt").write_text("Hello world.", encoding="utf-8")
    (invalid_dir / "reference.wav").write_bytes(b"RIFF" + b"\x00" * 128)

    with pytest.raises(LibraryIntegrityError, match=r"voice id must match"):
        list_voice_records(lib)


def test_save_voice_overwrite_rejects_non_directory_target_without_backup_debris(tmp_path):
    lib = tmp_path / "voices"
    target_path = lib / "blocked_voice"
    target_path.parent.mkdir(parents=True)
    target_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(InvalidInputError, match="path must be a directory"):
        save_voice_record(
            lib,
            make_design_draft("blocked_voice", reference_text="Updated sample."),
            _make_audio(),
            24000,
            overwrite=True,
        )

    assert target_path.read_text(encoding="utf-8") == "not a directory"
    assert list(lib.glob(".blocked_voice-backup-*")) == []
