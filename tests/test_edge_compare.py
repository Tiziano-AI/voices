"""Partial comparison preserves independently useful performances through HTTP."""

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from helpers import MOCK_AUDIO, seed_voice

from voices.domain.errors import GenerationError
from voices.edge.app import create_edge_app


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
