"""Coherent reference capture at the actual filesystem/runtime ownership seams."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import MagicMock

import numpy as np
import pytest
from helpers import MOCK_AUDIO, make_design_draft, seed_voice

from voices import config
from voices.adapter import mlx_qwen, mlx_runtime
from voices.domain.errors import InputConflictError, InvalidVoiceEntryError
from voices.domain.speech_contracts import SpeechModelIdentity, SpeechReferenceIdentity
from voices.store import library_store
from voices.store.output_store import output_artifact_for_name, save_existing_output
from voices.workflow import synthesize_voice


def overwrite(library, text="Reference B."):
    return library_store.save_voice_record(
        library, make_design_draft(reference_text=text), np.full(2400, 0.25, dtype=np.float32), 24000, overwrite=True
    )


@pytest.mark.parametrize("separate_process", [False, True])
def test_snapshot_owns_old_descriptors_when_overwrite_unlinks_old_directory(tmp_path, monkeypatch, separate_process):
    library = tmp_path / "library"
    original = seed_voice(library)
    original_bytes = (library / "test_voice" / "reference.wav").read_bytes()
    open_asset = library_store._open_voice_asset

    def open_then_replace(directory_fd, name, voice_id):
        handle = open_asset(directory_fd, name, voice_id)
        if name == library_store.REFERENCE_TEXT_NAME:
            if separate_process:
                # A real independent writer, without sharing a Python lock or mocks.
                code = """
import sys
from pathlib import Path
import numpy as np
from voices.domain.contracts import VoiceDraft
from voices.store.library_store import save_voice_record
draft = VoiceDraft.model_validate_json(sys.argv[2])
save_voice_record(Path(sys.argv[1]), draft, np.full(2400, .25, dtype=np.float32), 24000, overwrite=True)
"""
                draft = make_design_draft(reference_text="Reference B.")
                subprocess.run(
                    [sys.executable, "-c", code, str(library), draft.model_dump_json()], check=True, timeout=20
                )
            else:
                overwrite(library)
        return handle

    monkeypatch.setattr(library_store, "_open_voice_asset", open_then_replace)
    snapshot = library_store.load_voice_snapshot(library, "test_voice")
    assert snapshot.record == original
    assert snapshot.reference_audio == original_bytes
    assert snapshot.reference_text == "Hello world."
    assert snapshot.reference_text_sha256 == hashlib.sha256(b"Hello world.").hexdigest()
    monkeypatch.setattr(library_store, "_open_voice_asset", open_asset)
    assert library_store.load_voice_record(library, "test_voice").reference_text == "Reference B."
    assert not list(library.glob(".*-backup-*"))


def test_overwrite_before_all_descriptors_open_fails_without_synthesis(tmp_path, monkeypatch):
    library = tmp_path / "library"
    seed_voice(library)
    open_asset = library_store._open_voice_asset

    def open_then_replace(directory_fd, name, voice_id):
        handle = open_asset(directory_fd, name, voice_id)
        if name == library_store.VOICE_METADATA_NAME:
            overwrite(library)
        return handle

    synthesize = MagicMock(side_effect=AssertionError("must not synthesize an incomplete capture"))
    monkeypatch.setattr(library_store, "_open_voice_asset", open_then_replace)
    monkeypatch.setattr(synthesize_voice, "synthesize_reference_voice", synthesize)
    with pytest.raises(InvalidVoiceEntryError, match="changed during capture"):
        synthesize_voice.prepare_speech(voice_id="test_voice", text="Hello.", language=None, library=library)
    synthesize.assert_not_called()


@pytest.mark.parametrize("corruption", [None, "digest", "metadata", "transcript", "missing", "fifo", "symlink", "read"])
def test_capture_closes_every_descriptor_on_success_and_failure(tmp_path, monkeypatch, corruption):
    library = tmp_path / "library"
    seed_voice(library)
    directory = library / "test_voice"
    if corruption == "digest":
        (directory / "reference.wav").write_bytes(b"changed audio")
    elif corruption == "metadata":
        (directory / "voice.json").write_text("{malformed", encoding="utf-8")
    elif corruption == "transcript":
        (directory / "reference.txt").write_bytes(b"\xff")
    elif corruption in {"missing", "fifo", "symlink"}:
        (directory / "reference.txt").unlink()
        if corruption == "fifo":
            os.mkfifo(directory / "reference.txt")
        elif corruption == "symlink":
            (directory / "reference.txt").symlink_to(directory / "voice.json")
    opened = []
    real_open = library_store.os.open

    def track_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(library_store.os, "open", track_open)
    if corruption == "read":
        real_fdopen = library_store.os.fdopen

        class Unreadable:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.handle.close()

            def read(self):
                raise OSError("read failed")

        monkeypatch.setattr(library_store.os, "fdopen", lambda *args: Unreadable(real_fdopen(*args)))
    if corruption is None:
        library_store.load_voice_snapshot(library, "test_voice")
    else:
        with pytest.raises(InvalidVoiceEntryError, match="read failed" if corruption == "read" else None):
            library_store.load_voice_snapshot(library, "test_voice")
    assert opened
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_same_audio_with_changed_transcript_has_distinct_identity(tmp_path):
    first = seed_voice(tmp_path)
    second = library_store.save_voice_record(
        tmp_path, make_design_draft(reference_text="A corrected transcript."), MOCK_AUDIO, 24000, overwrite=True
    )
    assert first.reference_sha256 == second.reference_sha256
    assert first.reference_text_sha256 != second.reference_text_sha256


def test_capture_survives_lock_wait_overwrite_and_exports_original_bytes(tmp_path, monkeypatch):
    library, outputs = tmp_path / "library", tmp_path / "outputs"
    original = seed_voice(library)
    captured = Event()
    load_snapshot = synthesize_voice.load_voice_snapshot
    observed = {}

    def capture(*args):
        snapshot = load_snapshot(*args)
        captured.set()
        return snapshot

    runtime = MagicMock()
    runtime.sample_rate = 24000

    def generate(**kwargs):
        assert mlx_runtime._runtime_lock.locked()
        observed.update(kwargs)
        np.testing.assert_array_equal(np.array(kwargs["ref_audio"]), MOCK_AUDIO)
        yield MagicMock(audio=np.full(800, 0.125, dtype=np.float32))
        assert mlx_runtime._runtime_lock.locked()
        observed["exhausted"] = True

    runtime.generate.side_effect = generate
    monkeypatch.setattr(synthesize_voice, "load_voice_snapshot", capture)
    monkeypatch.setattr(mlx_qwen, "_get_runtime", lambda *_args: runtime)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with mlx_runtime.serialized_mlx_runtime():
            task = pool.submit(
                synthesize_voice.prepare_speech,
                voice_id="test_voice",
                text="  Keep original.  ",
                language=None,
                library=library,
            )
            assert captured.wait(timeout=5)
            replacement = overwrite(library)
        generated = task.result(timeout=5)
    assert observed["ref_text"] == original.reference_text
    assert observed["text"] == "Keep original."
    assert observed["exhausted"]
    assert generated.voice == original and generated.voice != replacement
    assert generated.output_draft.reference_sha256 == original.reference_sha256
    assert generated.output_draft.reference_text_sha256 == original.reference_text_sha256
    preview_path = tmp_path / "preview.wav"
    library_store.write_wav(preview_path, generated.audio, generated.sample_rate)
    preview_bytes = preview_path.read_bytes()
    library_store.delete_voice_record(library, "test_voice")
    path = save_existing_output(outputs, generated.output_draft, preview_path)
    assert path.read_bytes() == preview_bytes
    artifact = output_artifact_for_name(outputs, "test_voice", path.name)
    assert artifact.record.reference_sha256 == original.reference_sha256
    assert artifact.record.reference_text_sha256 == original.reference_text_sha256
    assert json.loads(path.with_suffix(".json").read_text())["text"] == "Keep original."


@pytest.mark.parametrize("change", ["audio", "transcript", "model"])
@pytest.mark.parametrize("persist", [False, True])
def test_preconditions_refuse_changed_inputs_before_runtime_observation(tmp_path, monkeypatch, change, persist):
    original = seed_voice(tmp_path)
    expected_reference = SpeechReferenceIdentity(
        reference_sha256=original.reference_sha256, reference_text_sha256=original.reference_text_sha256
    )
    expected_model = SpeechModelIdentity(
        base_model_id=config.BASE_MODEL, base_model_revision=config.BASE_MODEL_REVISION
    )
    if change == "audio":
        overwrite(tmp_path, original.reference_text)
    elif change == "transcript":
        library_store.save_voice_record(
            tmp_path, make_design_draft(reference_text="Different words."), MOCK_AUDIO, 24000, overwrite=True
        )
    else:
        monkeypatch.setattr(config, "BASE_MODEL_REVISION", "d" * 40)
    observe = MagicMock(side_effect=AssertionError("no runtime admission on conflict"))
    monkeypatch.setattr(synthesize_voice, "get_runtime_identity", observe)
    monkeypatch.setattr(synthesize_voice, "synthesize_reference_voice", observe)
    kwargs = dict(
        voice_id="test_voice",
        text="Hello.",
        language=None,
        library=tmp_path,
        expected_reference=expected_reference,
        expected_model=expected_model,
    )
    with pytest.raises(InputConflictError, match="Refresh"):
        if persist:
            synthesize_voice.render_speech(out_dir=tmp_path / "out", **kwargs)
        else:
            synthesize_voice.prepare_speech(**kwargs)
    observe.assert_not_called()
    assert not (tmp_path / "out").exists()
