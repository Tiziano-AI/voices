"""Exact preview publication through the real local edge and output store."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from helpers import MOCK_AUDIO, seed_voice

from voices import config
from voices.edge.app import create_edge_app
from voices.runtime_identity import RuntimeIdentity
from voices.store import output_store
from voices.workflow import synthesize_voice


@pytest.fixture
def studio(tmp_path, monkeypatch):
    library, out = tmp_path / "library", tmp_path / "outputs"
    voice = seed_voice(library)
    audio = np.linspace(-0.4, 0.4, 2400, dtype=np.float32)
    synthesize = MagicMock(return_value=(audio, 24000))
    identity = RuntimeIdentity(
        python="fixture-python",
        executable="/fixture/python",
        platform="fixture-platform",
        voices_version="fixture-version",
        source_sha256="b" * 64,
        packages={"mlx-audio": "fixture-version"},
    )
    monkeypatch.setattr(synthesize_voice, "synthesize_reference_voice", synthesize)
    monkeypatch.setattr(synthesize_voice, "get_runtime_identity", lambda: identity)
    monkeypatch.setattr(synthesize_voice, "utc_now", lambda: "2026-10-19T12:00:00Z")
    app = create_edge_app(library=library, out_dir=out, web_dist=None)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client, app.state.context, voice, identity, synthesize


def preview(client):
    response = client.post("/api/preview", json={"voice_id": "test_voice", "text": "Keep this performance."})
    assert response.status_code == 200, response.text
    return response.json()


def test_export_keeps_exact_wav_and_generation_provenance_after_inputs_change(studio, monkeypatch):
    client, context, voice, identity, synthesize = studio
    model, revision = config.BASE_MODEL, config.BASE_MODEL_REVISION
    clip = preview(client)
    auditioned = client.get(clip["audio_url"]).content
    assert not context.out_dir.exists()
    monkeypatch.setattr(config, "BASE_MODEL", "different/model")
    monkeypatch.setattr(config, "BASE_MODEL_REVISION", "c" * 40)
    monkeypatch.setattr(
        synthesize_voice, "get_runtime_identity", MagicMock(side_effect=AssertionError("late identity"))
    )
    monkeypatch.setattr(
        synthesize_voice, "load_voice_snapshot", MagicMock(side_effect=AssertionError("late reference"))
    )
    synthesize.side_effect = AssertionError("export must not synthesize")

    response = client.post(f"/api/previews/{clip['token']}/export")
    assert response.status_code == 200, response.text
    artifact = response.json()
    assert client.get(artifact["audio_url"]).content == auditioned
    record = client.get(artifact["sidecar_url"]).json()
    assert record == artifact["record"]
    assert record["text"] == "Keep this performance."
    assert record["created_at"] == "2026-10-19T12:00:00Z"
    assert record["language"] == voice.language
    assert record["reference_sha256"] == voice.reference_sha256
    assert record["reference_text_sha256"] == voice.reference_text_sha256
    assert record["base_model_id"] == model
    assert record["base_model_revision"] == revision
    assert record["runtime"] == identity.model_dump(mode="json")
    synthesize.assert_called_once()


def test_repeated_and_concurrent_export_reuses_one_persisted_pair(studio):
    client, context, _voice, _identity, synthesize = studio
    clip = preview(client)
    url = f"/api/previews/{clip['token']}/export"
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url), range(8)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    assert len(list(context.out_dir.rglob("*.wav"))) == 1
    assert len(list(context.out_dir.rglob("*.json"))) == 1
    synthesize.assert_called_once()


def test_unknown_review_and_missing_preview_audio_cannot_export(studio):
    client, context, _voice, _identity, synthesize = studio
    review = context.asset_store.save_review_audio(MOCK_AUDIO, "English", "test_voice")
    clip = preview(client)
    context.asset_store.asset_path(clip["token"]).unlink()
    for token in ("unknown", review.review_token, clip["token"]):
        response = client.post(f"/api/previews/{token}/export")
        assert response.status_code == 404, response.text
        assert "Preview expired or not found" in response.json()["detail"]
    assert not context.out_dir.exists()
    synthesize.assert_called_once()


def test_cross_origin_export_is_rejected_without_publication(studio):
    client, context, _voice, _identity, _synthesize = studio
    clip = preview(client)
    response = client.post(f"/api/previews/{clip['token']}/export", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 400
    assert not context.out_dir.exists()


def test_export_uses_output_root_safety_boundary(studio, tmp_path):
    client, context, _voice, _identity, _synthesize = studio
    clip = preview(client)
    outside = tmp_path / "outside"
    outside.mkdir()
    context.out_dir.symlink_to(outside, target_is_directory=True)
    response = client.post(f"/api/previews/{clip['token']}/export")
    assert response.status_code == 400
    assert "must not be a symlink" in response.json()["detail"]
    assert list(outside.iterdir()) == []


def test_partial_copy_failure_cleans_staging_and_keeps_preview_retryable(studio, monkeypatch):
    client, context, _voice, _identity, _synthesize = studio
    clip = preview(client)
    copy = output_store.shutil.copyfile

    def fail_copy(_source, destination):
        Path(destination).write_bytes(b"partial")
        raise OSError("synthetic copy failure")

    monkeypatch.setattr(output_store.shutil, "copyfile", fail_copy)
    with pytest.raises(OSError, match="synthetic copy failure"):
        client.post(f"/api/previews/{clip['token']}/export")
    assert [path.name for path in (context.out_dir / "test_voice").iterdir()] == [".render.lock"]
    monkeypatch.setattr(output_store.shutil, "copyfile", copy)
    assert client.post(f"/api/previews/{clip['token']}/export").status_code == 200
