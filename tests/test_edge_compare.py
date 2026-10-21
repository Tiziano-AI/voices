"""Partial comparison preserves independently useful performances through HTTP."""

import errno
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from helpers import MOCK_AUDIO, seed_voice

from voices.domain.errors import GenerationError
from voices.edge import storage
from voices.edge.app import create_edge_app
from voices.edge.contracts import PreviewRequest
from voices.edge.service import StudioContext, create_preview_clip
from voices.store import library_store


@patch("voices.workflow.synthesize_voice.synthesize_reference_voice")
def test_compare_keeps_successful_audio_and_export_when_another_voice_fails(mock_synthesize, tmp_path: Path):
    library = tmp_path / "voices"
    for voice_id in ("alpha_voice", "beta_voice", "gamma_voice"):
        seed_voice(library, voice_id)
    app = create_edge_app(library=library, out_dir=tmp_path / "outputs", web_dist=None)
    mock_synthesize.side_effect = [
        (MOCK_AUDIO, 24000),
        GenerationError("Synthetic generation failure."),
        (MOCK_AUDIO, 24000),
    ]

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/api/compare",
            json={"voice_ids": ["alpha_voice", "beta_voice", "gamma_voice"], "text": "Keep every success."},
        )
        assert response.status_code == 200, response.text
        alpha, beta, gamma = response.json()
        assert [row["voice_id"] for row in (alpha, beta, gamma)] == ["alpha_voice", "beta_voice", "gamma_voice"]
        assert alpha["error"] is None and gamma["error"] is None
        assert beta == {
            "voice_id": "beta_voice",
            "clip": None,
            "error": {"error_code": "GenerationError", "detail": "Synthetic generation failure."},
        }
        for result in (alpha, gamma):
            clip = result["clip"]
            audio = client.get(clip["audio_url"])
            export = client.post(f"/api/previews/{clip['token']}/export")
            assert audio.status_code == export.status_code == 200
            assert client.get(export.json()["audio_url"]).content == audio.content
            assert export.json()["record"]["voice_id"] == result["voice_id"]
    assert mock_synthesize.call_count == 3


@pytest.mark.parametrize("failure", ["preview-write", "reference-directory", "reference-read"])
@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_compare_keeps_successful_tokens_through_voice_io_failure(mock_synthesize, tmp_path, monkeypatch, failure):
    library = tmp_path / "voices"
    for voice_id in ("alpha_voice", "beta_voice", "gamma_voice"):
        seed_voice(library, voice_id)
    app = create_edge_app(library=library, out_dir=tmp_path / "outputs", web_dist=None)
    failing = True
    write_count = 0
    write_wav = storage.write_wav
    open_directory = library_store.os.open
    open_asset = library_store._open_voice_asset

    def write_preview(path, audio, sample_rate):
        nonlocal write_count
        write_count += 1
        if failing and failure == "preview-write" and write_count == 2:
            path.write_bytes(b"incomplete WAV")
            raise OSError(errno.ENOSPC, "No space left on device")
        write_wav(path, audio, sample_rate)

    def open_reference_directory(path, flags, *args, **kwargs):
        if failing and failure == "reference-directory" and path == library / "beta_voice":
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return open_directory(path, flags, *args, **kwargs)

    class Unreadable:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.handle.close()

        def read(self):
            raise OSError(errno.EIO, "Input/output error")

    def open_reference_asset(directory_fd, name, voice_id):
        handle = open_asset(directory_fd, name, voice_id)
        if failing and failure == "reference-read" and voice_id == "beta_voice":
            return Unreadable(handle)
        return handle

    monkeypatch.setattr(storage, "write_wav", write_preview)
    monkeypatch.setattr(library_store.os, "open", open_reference_directory)
    monkeypatch.setattr(library_store, "_open_voice_asset", open_reference_asset)
    with TestClient(app, base_url="http://127.0.0.1:8765", raise_server_exceptions=False) as client:
        response = client.post(
            "/api/compare",
            json={"voice_ids": ["alpha_voice", "beta_voice", "gamma_voice"], "text": "Keep the successful audio."},
        )
        assert response.status_code == 200, response.text
        alpha, beta, gamma = response.json()
        assert beta["clip"] is None
        expected_error = "PreviewStorageError" if failure == "preview-write" else "InvalidVoiceEntryError"
        assert beta["error"]["error_code"] == expected_error
        assert "beta_voice" in beta["error"]["detail"]
        expected_cause = {
            "preview-write": "No space left on device",
            "reference-directory": "Permission denied",
            "reference-read": "Input/output error",
        }[failure]
        assert expected_cause in beta["error"]["detail"]
        assert str(library) not in beta["error"]["detail"]
        assert "Check" in beta["error"]["detail"]
        assert len(list(app.state.context.asset_store.root.glob("*.wav"))) == 2
        generation_count = mock_synthesize.call_count
        assert generation_count == (3 if failure == "preview-write" else 2)
        for result in (alpha, gamma):
            assert result["error"] is None
            clip = result["clip"]
            audio = client.get(clip["audio_url"])
            export = client.post(f"/api/previews/{clip['token']}/export")
            assert audio.status_code == export.status_code == 200
            assert client.get(export.json()["audio_url"]).content == audio.content
        assert mock_synthesize.call_count == generation_count
        if failure == "preview-write":
            write_count = 1
        preview = client.post("/api/preview", json={"voice_id": "beta_voice", "text": "Still unavailable."})
        assert preview.status_code == (503 if failure == "preview-write" else 409)
        assert preview.json()["error_code"] == expected_error
        calls_before_retry = mock_synthesize.call_count
        failing = False
        retried = client.post("/api/compare", json={"voice_ids": ["beta_voice"], "text": "Keep the successful audio."})
        assert retried.status_code == 200
        assert retried.json()[0]["voice_id"] == "beta_voice" and retried.json()[0]["error"] is None
        assert mock_synthesize.call_count == calls_before_retry + 1
        assert client.get(alpha["clip"]["audio_url"]).status_code == 200


@pytest.mark.parametrize("boundary", ["reference", "preview"])
@pytest.mark.parametrize("error_type", [TypeError, KeyboardInterrupt])
@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_voice_io_boundaries_do_not_hide_programming_errors_or_interrupts(
    _mock_synthesize, tmp_path, monkeypatch, boundary, error_type
):
    library = tmp_path / "voices"
    seed_voice(library, "alpha_voice")
    context = StudioContext(library=library, out_dir=tmp_path / "outputs", asset_store=storage.StudioAssetStore())
    open_directory = library_store.os.open

    def fail_preview(*_args):
        raise error_type("Synthetic non-I/O failure.")

    def open_reference_directory(path, flags, *args, **kwargs):
        if path == library / "alpha_voice":
            raise error_type("Synthetic non-I/O failure.")
        return open_directory(path, flags, *args, **kwargs)

    if boundary == "preview":
        monkeypatch.setattr(storage, "write_wav", fail_preview)
    else:
        monkeypatch.setattr(library_store.os, "open", open_reference_directory)
    try:
        with pytest.raises(error_type, match="Synthetic non-I/O failure"):
            create_preview_clip(context, PreviewRequest(voice_id="alpha_voice", text="Do not hide this error."))
    finally:
        context.asset_store.cleanup()
