import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import MOCK_AUDIO, seed_voice

from voices import config
from voices.domain.create_contracts import TranscriptionDraft
from voices.domain.errors import InvalidInputError
from voices.edge.app import create_edge_app
from voices.workflow.clone_voice import PreparedCloneReview


def _client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    library = tmp_path / "voices"
    out_dir = tmp_path / "outputs"
    app = create_edge_app(library=library, out_dir=out_dir, web_dist=None)
    return TestClient(app, base_url="http://127.0.0.1:8765"), library, out_dir


def test_ui_config_exposes_guided_scripts(tmp_path: Path):
    client, _library, _out_dir = _client(tmp_path)

    with client:
        response = client.get("/api/ui-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_language"] == "English"
    assert "English" in payload["supported_languages"]
    assert "English" in payload["guided_scripts"]


def test_list_and_detail_project_saved_voice(tmp_path: Path):
    client, library, _out_dir = _client(tmp_path)
    seed_voice(library, "deep_voice")

    with client:
        list_response = client.get("/api/voices")
        detail_response = client.get("/api/voices/deep_voice")
        audio_response = client.get("/api/voices/deep_voice/reference-audio")

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == "deep_voice"
    assert detail_response.status_code == 200
    assert detail_response.json()["record"]["id"] == "deep_voice"
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"] == "audio/wav"


@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_preview_is_ephemeral(mock_synthesize, tmp_path: Path):
    client, library, out_dir = _client(tmp_path)
    seed_voice(library, "deep_voice")

    with client:
        response = client.post(
            "/api/preview",
            json={"voice_id": "deep_voice", "text": "We proceed at dawn.", "language": "English"},
        )
        clip = response.json()
        audio_response = client.get(clip["audio_url"])

    assert response.status_code == 200
    assert clip["kind"] == "generated"
    assert audio_response.status_code == 200
    assert not out_dir.exists()
    mock_synthesize.assert_called_once()


@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_compare_returns_ordered_ephemeral_clips(mock_synthesize, tmp_path: Path):
    client, library, out_dir = _client(tmp_path)
    seed_voice(library, "alpha_voice")
    seed_voice(library, "beta_voice")

    with client:
        response = client.post(
            "/api/compare",
            json={"voice_ids": ["alpha_voice", "beta_voice"], "text": "Compare this.", "language": "English"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [row["voice_id"] for row in payload] == ["alpha_voice", "beta_voice"]
    assert all(row["audio_url"].startswith("/api/assets/") for row in payload)
    assert not out_dir.exists()
    assert mock_synthesize.call_count == 2


@patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000))
def test_render_persists_and_exposes_downloads(mock_synthesize, tmp_path: Path):
    client, library, out_dir = _client(tmp_path)
    seed_voice(library, "deep_voice")

    with client:
        response = client.post(
            "/api/render",
            json={"voice_id": "deep_voice", "text": "Ship it.", "language": "English"},
        )
        payload = response.json()
        wav_response = client.get(payload["audio_url"])
        sidecar_response = client.get(payload["sidecar_url"])

    assert response.status_code == 200
    assert payload["record"]["voice_id"] == "deep_voice"
    assert wav_response.status_code == 200
    assert sidecar_response.status_code == 200
    assert (out_dir / "deep_voice").exists()
    mock_synthesize.assert_called_once()


def test_output_download_rejects_symlinked_file(tmp_path: Path):
    client, _library, out_dir = _client(tmp_path)
    voice_out_dir = out_dir / "deep_voice"
    voice_out_dir.mkdir(parents=True)
    outside_file = tmp_path / "outside.json"
    outside_file.write_text('{"secret": true}', encoding="utf-8")
    (voice_out_dir / "20260408T120000Z__leak.json").symlink_to(outside_file)

    with client:
        response = client.get("/api/outputs/deep_voice/20260408T120000Z__leak.json")

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"


def test_output_download_rejects_symlinked_output_directory(tmp_path: Path):
    client, _library, out_dir = _client(tmp_path)
    real_dir = out_dir / "real_voice"
    real_dir.mkdir(parents=True)
    (real_dir / "20260408T120000Z__clip.wav").write_bytes(b"RIFF")
    (out_dir / "alias_voice").symlink_to(real_dir, target_is_directory=True)

    with client:
        response = client.get("/api/outputs/alias_voice/20260408T120000Z__clip.wav")

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"


def test_output_download_rejects_symlinked_output_root(tmp_path: Path):
    real_out_dir = tmp_path / "real-outputs"
    real_out_dir.mkdir()
    out_dir = tmp_path / "outputs"
    out_dir.symlink_to(real_out_dir, target_is_directory=True)
    voice_out_dir = real_out_dir / "deep_voice"
    voice_out_dir.mkdir()
    (voice_out_dir / "20260408T120000Z__clip.wav").write_bytes(b"RIFF")
    app = create_edge_app(library=tmp_path / "voices", out_dir=out_dir, web_dist=None)
    client = TestClient(app, base_url="http://127.0.0.1:8765")

    with client:
        response = client.get("/api/outputs/deep_voice/20260408T120000Z__clip.wav")

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"


def test_output_download_rejects_non_artifact_filename(tmp_path: Path):
    client, _library, out_dir = _client(tmp_path)
    voice_out_dir = out_dir / "deep_voice"
    voice_out_dir.mkdir(parents=True)
    (voice_out_dir / "private.txt").write_text("secret=1", encoding="utf-8")

    with client:
        response = client.get("/api/outputs/deep_voice/private.txt")

    assert response.status_code == 400
    assert response.json()["error_code"] == "RequestValidationError"


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_mutating_request_rejects_cross_origin(mock_design_audio, tmp_path: Path):
    client, library, _out_dir = _client(tmp_path)
    prompt_pack = b'{"id":"evil_voice","name":"Evil Voice","instruct":"Warm narrator","text":"Hello."}\n'

    with client:
        response = client.post(
            "/api/design/batch",
            files={"file": ("pack.jsonl", prompt_pack, "application/jsonl")},
            data={"language": "English", "dry_run": "false"},
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    assert not (library / "evil_voice").exists()
    mock_design_audio.assert_not_called()


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_mutating_request_rejects_malformed_loopback_origin(mock_design_audio, tmp_path: Path):
    app = create_edge_app(library=tmp_path / "voices", out_dir=tmp_path / "outputs", web_dist=None)
    client = TestClient(app, base_url="http://localhost:80")

    with client:
        response = client.post(
            "/api/design",
            json={
                "name": "Noir Narrator",
                "voice_id": "noir_narrator",
                "instruct": "Low, smoky, restrained authority.",
                "text": "Control is not the absence of feeling.",
                "language": "English",
                "overwrite": False,
            },
            headers={"Origin": "http://localhost:notaport"},
        )

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    mock_design_audio.assert_not_called()


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_multipart_content_length_preflight_rejects_declared_oversize(
    mock_design_audio,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    client, _library, _out_dir = _client(tmp_path)
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1)

    with client:
        response = client.post(
            "/api/design/batch",
            files={"file": ("pack.jsonl", b"x" * (70 * 1024), "application/jsonl")},
            data={"language": "English", "dry_run": "true"},
        )

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    mock_design_audio.assert_not_called()


@patch("voices.workflow.design_voice.design_reference_audio", return_value=(MOCK_AUDIO, 24000))
def test_design_creates_voice_through_api(mock_design_audio, tmp_path: Path):
    client, library, _out_dir = _client(tmp_path)

    with client:
        response = client.post(
            "/api/design",
            json={
                "name": "Noir Narrator",
                "voice_id": "noir_narrator",
                "instruct": "Low, smoky, restrained authority.",
                "text": "Control is not the absence of feeling.",
                "language": "English",
                "overwrite": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["record"]["id"] == "noir_narrator"
    assert (library / "noir_narrator" / "voice.json").exists()
    mock_design_audio.assert_called_once()


def test_preview_generation_does_not_block_ui_config(tmp_path: Path):
    library = tmp_path / "voices"
    seed_voice(library, "deep_voice")
    app = create_edge_app(library=library, out_dir=tmp_path / "outputs", web_dist=None)

    def slow_synthesis(*_args: object, **_kwargs: object):
        time.sleep(0.35)
        return MOCK_AUDIO, 24000

    async def run_probe() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as async_client:
            with patch("voices.workflow.synthesize_voice.synthesize_reference_voice", side_effect=slow_synthesis):
                preview_task = asyncio.create_task(
                    async_client.post(
                        "/api/preview",
                        json={"voice_id": "deep_voice", "text": "We proceed at dawn.", "language": "English"},
                    )
                )
                await asyncio.sleep(0.05)
                started_at = time.perf_counter()
                config_response = await async_client.get("/api/ui-config")
                elapsed = time.perf_counter() - started_at
                preview_response = await preview_task
        assert config_response.status_code == 200
        assert preview_response.status_code == 200
        assert elapsed < 0.2

    asyncio.run(run_probe())


@patch(
    "voices.edge.service.prepare_clone_review",
    return_value=PreparedCloneReview(
        draft=TranscriptionDraft(
            transcript="Hello from local STT.",
            language="English",
            duration_seconds=4.0,
            segments=[],
        ),
        normalized_audio=MOCK_AUDIO,
        suggested_voice_id="stage-voice",
    ),
)
@patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=MOCK_AUDIO)
def test_clone_review_and_save_workflow(
    mock_clone_convert,
    mock_prepare_review,
    tmp_path: Path,
):
    client, library, _out_dir = _client(tmp_path)
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"RIFF" + b"\x00" * 200)

    with client:
        with source_audio.open("rb") as input_file:
            review_response = client.post(
                "/api/clone/review",
                files={"audio": ("source.wav", input_file, "audio/wav")},
                data={"language": "English", "name": "Stage Voice", "review_policy": "import"},
            )
        review_payload = review_response.json()
        save_response = client.post(
            "/api/clone/save",
            json={
                "review_token": review_payload["review_token"],
                "voice_id": "stage-voice",
                "name": "Stage Voice",
                "transcript": "Approved transcript.",
                "overwrite": False,
            },
        )

    assert review_response.status_code == 200
    assert review_payload["transcript"] == "Hello from local STT."
    assert review_payload["audio_url"].startswith("/api/assets/")
    assert save_response.status_code == 200
    assert save_response.json()["record"]["source"]["kind"] == "clone"
    assert (library / "stage-voice" / "reference.wav").exists()
    mock_prepare_review.assert_called_once()
    mock_clone_convert.assert_called_once()

    with client:
        repeated_save = client.post(
            "/api/clone/save",
            json={
                "review_token": review_payload["review_token"],
                "voice_id": "stage-voice-2",
                "name": "Stage Voice 2",
                "transcript": "Approved transcript.",
                "overwrite": False,
            },
        )

    assert repeated_save.status_code == 404
    assert repeated_save.json()["error_code"] == "VoiceNotFoundError"


def test_clone_review_rejects_blank_multipart_fields_as_json_error(tmp_path: Path):
    client, _library, _out_dir = _client(tmp_path)
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"RIFF" + b"\x00" * 200)

    with client:
        with source_audio.open("rb") as input_file:
            response = client.post(
                "/api/clone/review",
                files={"audio": ("source.wav", input_file, "audio/wav")},
                data={"language": "English", "transcript": "   "},
            )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error_code"] == "RequestValidationError"


def test_batch_design_rejects_blank_shared_text_as_json_error(tmp_path: Path):
    client, _library, _out_dir = _client(tmp_path)
    prompt_pack = b'{"id":"dry_voice","name":"Dry Voice","instruct":"Warm narrator","text":"Hello."}\n'

    with client:
        response = client.post(
            "/api/design/batch",
            files={"file": ("pack.jsonl", prompt_pack, "application/jsonl")},
            data={"language": "English", "text": "   ", "dry_run": "true"},
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error_code"] == "RequestValidationError"


def test_batch_design_rejects_oversized_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, _library, _out_dir = _client(tmp_path)
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 8)

    with client:
        upload = b'{"id":"v","instruct":"Warm narrator","text":"Hello."}\n'
        response = client.post(
            "/api/design/batch",
            files={"file": ("pack.jsonl", upload, "application/jsonl")},
            data={"language": "English", "dry_run": "true"},
        )

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"


@patch(
    "voices.edge.service.prepare_clone_review",
    side_effect=InvalidInputError("Recorded take must be at least 3s before transcript review."),
)
def test_record_free_review_rejects_short_take(mock_prepare_review, tmp_path: Path):
    client, _library, _out_dir = _client(tmp_path)
    source_audio = tmp_path / "source.wav"
    source_audio.write_bytes(b"RIFF" + b"\x00" * 200)

    with client:
        with source_audio.open("rb") as input_file:
            response = client.post(
                "/api/clone/review",
                files={"audio": ("source.wav", input_file, "audio/wav")},
                data={"language": "English", "review_policy": "record_free"},
            )

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    mock_prepare_review.assert_called_once()


def test_delete_voice_updates_library(tmp_path: Path):
    client, library, _out_dir = _client(tmp_path)
    seed_voice(library, "discard_me")

    with client:
        delete_response = client.delete("/api/voices/discard_me")
        list_response = client.get("/api/voices")

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert list_response.json() == []


def test_invalid_library_returns_conflict(tmp_path: Path):
    client, library, _out_dir = _client(tmp_path)
    broken = library / "Bad-ID"
    broken.mkdir(parents=True)
    (broken / "voice.json").write_text("{}", encoding="utf-8")
    (broken / "reference.txt").write_text("Hello world.", encoding="utf-8")
    (broken / "reference.wav").write_bytes(b"RIFF" + b"\x00" * 200)

    with client:
        response = client.get("/api/voices")

    assert response.status_code == 409
    assert response.json()["error_code"] == "LibraryIntegrityError"


def test_invalid_library_returns_conflict_for_non_directory_entry(tmp_path: Path):
    client, library, _out_dir = _client(tmp_path)
    library.mkdir(parents=True)
    (library / "ghost_voice").write_text("not a directory", encoding="utf-8")

    with client:
        response = client.get("/api/voices")

    assert response.status_code == 409
    assert response.json()["error_code"] == "LibraryIntegrityError"
