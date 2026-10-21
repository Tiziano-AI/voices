"""Effective performance identity and preconditions through the real HTTP surface."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from helpers import MOCK_AUDIO, make_design_draft, seed_voice

from voices import config
from voices.edge.app import create_edge_app
from voices.store.library_store import save_voice_record
from voices.workflow import synthesize_voice


@pytest.fixture
def studio(tmp_path, monkeypatch):
    library = tmp_path / "library"
    seed_voice(library)
    synthesize = MagicMock(return_value=(MOCK_AUDIO, 24000))
    monkeypatch.setattr(synthesize_voice, "synthesize_reference_voice", synthesize)
    app = create_edge_app(library=library, out_dir=tmp_path / "outputs", web_dist=None)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client, library, synthesize


def selected_input(client):
    voice = client.get("/api/voices").json()[0]
    model = client.get("/api/ui-config").json()
    return {
        "voice_id": voice["id"],
        "text": "  Keep the actual words.  ",
        "language": voice["language"],
        "expected_reference": {key: voice[key] for key in ("reference_sha256", "reference_text_sha256")},
        "expected_model": {key: model[key] for key in ("base_model_id", "base_model_revision")},
    }


def test_preview_returns_effective_input_and_export_keeps_it(studio):
    client, _library, synthesize = studio
    request = selected_input(client)
    response = client.post("/api/preview", json=request)
    assert response.status_code == 200, response.text
    clip = response.json()
    assert clip["input"] == {
        "voice_id": request["voice_id"],
        "text": request["text"].strip(),
        "language": "English",
        **request["expected_reference"],
        **request["expected_model"],
    }
    assert synthesize.call_args.kwargs["text"] == clip["input"]["text"]
    artifact = client.post(f"/api/previews/{clip['token']}/export").json()["record"]
    for key, value in clip["input"].items():
        assert artifact[key] == value


@pytest.mark.parametrize("route", ["preview", "render", "compare"])
@pytest.mark.parametrize("changed", ["audio", "transcript", "model"])
def test_changed_selection_fails_before_inference(studio, monkeypatch, route, changed):
    client, library, synthesize = studio
    request = selected_input(client)
    if changed == "model":
        monkeypatch.setattr(config, "BASE_MODEL_REVISION", "f" * 40)
    else:
        save_voice_record(
            library,
            make_design_draft(reference_text="A different transcript." if changed == "transcript" else "Hello world."),
            MOCK_AUDIO + (0.2 if changed == "audio" else 0),
            24000,
            overwrite=True,
        )
    if route == "compare":
        request["voice_ids"] = [request.pop("voice_id")]
        request["expected_references"] = {"test_voice": request.pop("expected_reference")}
    response = client.post(f"/api/{route}", json=request)
    assert response.status_code == (200 if route == "compare" else 409), response.text
    error = response.json()[0]["error"] if route == "compare" else response.json()
    assert error["error_code"] == "InputConflictError"
    assert "Refresh" in error["detail"]
    synthesize.assert_not_called()


def test_display_name_change_does_not_invalidate_selection(studio):
    client, library, synthesize = studio
    request = selected_input(client)
    save_voice_record(library, make_design_draft(name="Renamed narrator"), MOCK_AUDIO, 24000, overwrite=True)
    response = client.post("/api/preview", json=request)
    assert response.status_code == 200, response.text
    synthesize.assert_called_once()


def test_compare_resolves_saved_languages_and_carries_each_reference(studio):
    client, library, synthesize = studio
    save_voice_record(library, make_design_draft("second", language="Italian"), MOCK_AUDIO, 24000)
    voices = client.get("/api/voices").json()
    response = client.post(
        "/api/compare",
        json={
            "voice_ids": [voice["id"] for voice in voices],
            "text": "Say this.",
            "expected_references": {
                voice["id"]: {key: voice[key] for key in ("reference_sha256", "reference_text_sha256")}
                for voice in voices
            },
            "expected_model": selected_input(client)["expected_model"],
            "expected_languages": {voice["id"]: voice["language"] for voice in voices},
        },
    )
    assert response.status_code == 200, response.text
    assert [result["clip"]["input"]["language"] for result in response.json()] == ["English", "Italian"]
    assert synthesize.call_count == 2


def test_compare_rejects_changed_saved_language_before_runtime_admission(studio, monkeypatch):
    client, library, synthesize = studio
    selected = selected_input(client)
    save_voice_record(library, make_design_draft(language="Italian"), MOCK_AUDIO, 24000, overwrite=True)
    runtime = MagicMock(side_effect=AssertionError("Runtime admission must follow input validation"))
    monkeypatch.setattr(synthesize_voice, "get_runtime_identity", runtime)
    response = client.post(
        "/api/compare",
        json={
            "voice_ids": [selected["voice_id"]],
            "text": selected["text"],
            "expected_references": {selected["voice_id"]: selected["expected_reference"]},
            "expected_model": selected["expected_model"],
            "expected_languages": {selected["voice_id"]: selected["language"]},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()[0]
    assert result["clip"] is None
    assert result["error"]["error_code"] == "InputConflictError"
    assert "language changed" in result["error"]["detail"]
    runtime.assert_not_called()
    synthesize.assert_not_called()


def test_compare_rejects_invalid_expected_language_without_inference(studio):
    client, _library, synthesize = studio
    response = client.post(
        "/api/compare",
        json={"voice_ids": ["test_voice"], "text": "Say this.", "expected_languages": {"test_voice": "not-a-language"}},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    synthesize.assert_not_called()
