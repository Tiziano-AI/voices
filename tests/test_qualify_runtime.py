"""Deterministic checks only: the real qualification command is opt-in."""

import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from devtools import qualify_runtime as qualification
from voices.domain.create_contracts import TranscriptionDraft
from voices.store.library_store import write_wav


def test_transcript_comparison_retains_accents_and_reports_edge_omissions():
    comparison = qualification.transcript_comparison("Prima: una voce è chiara, fine.", "Una voce è chiara")
    assert comparison["word_edit_distance"] == 2
    assert comparison["word_error_rate"] == pytest.approx(2 / 6)
    assert comparison["leading_reference_omissions"] == ["prima"]
    assert comparison["trailing_reference_omissions"] == ["fine"]
    assert qualification.normalized_words("È L'IDEA!") == ["è", "l", "idea"]


def test_transcript_comparison_separates_substitution_and_insertion():
    comparison = qualification.transcript_comparison("the blue bird sings", "the red bird sings today")
    assert comparison["substitutions"] == 1
    assert comparison["insertions"] == 1
    assert comparison["deletions"] == 0
    assert comparison["word_error_rate"] == 0.5


def test_audio_metrics_measure_persisted_pcm(tmp_path):
    path = tmp_path / "sample.wav"
    write_wav(path, np.array([0, 0.5, -1, 1], dtype=np.float32), 24000)
    result = qualification.audio_metrics(path)
    assert result["samples"] == 4
    assert result["duration_seconds"] == 4 / 24000
    assert result["peak_amplitude"] == 1
    assert result["clipping_fraction"] == 0.5


def test_existing_root_is_refused_without_changes(tmp_path):
    marker = tmp_path / "owned.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        qualification.Qualification(tmp_path)
    assert list(tmp_path.iterdir()) == [marker]


def test_dangling_symlink_root_is_refused(tmp_path):
    target = tmp_path / "missing"
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        qualification.Qualification(link)
    assert not target.exists()


def test_user_library_descendant_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(qualification.config, "get_library_path", lambda: tmp_path / "library")
    with pytest.raises(ValueError, match="outside the user voice library"):
        qualification.Qualification(tmp_path / "library" / "new-run")
    assert not (tmp_path / "library").exists()


def test_failed_step_preserves_pending_effect_and_does_not_retry(tmp_path):
    run = qualification.Qualification(tmp_path / "new-run")
    artifact = run.out / "effect.txt"
    with pytest.raises(RuntimeError, match="after save"):
        with run.step("example", expected_artifact=str(artifact)):
            artifact.write_text("retained")
            raise RuntimeError("after save")
    report = json.loads((run.out / "report.json").read_text())
    events = [json.loads(line) for line in (run.out / "events.jsonl").read_text().splitlines()]
    assert report["events"] == events
    assert [event["state"] for event in events] == ["started", "started", "failed"]
    assert events[1]["expected_artifact"] == str(artifact)
    assert artifact.read_text() == "retained"


def test_qualification_text_lengths_cover_short_references_and_long_speech():
    for text in qualification.REFERENCES.values():
        assert 25 <= len(qualification.normalized_words(text)) <= 35
    for text in qualification.LONG_TEXTS.values():
        assert 100 <= len(qualification.normalized_words(text)) <= 130
        assert "\n" in text


def test_clone_review_receives_audio_only_and_save_uses_actual_asr_draft(tmp_path, monkeypatch):
    run = qualification.Qualification(tmp_path / "new-run")
    draft = TranscriptionDraft(transcript="Observed audio words.", language="English", duration_seconds=3, segments=[])

    def review(*, audio_path, library, request):
        assert audio_path == run.library / "design-english" / "reference.wav"
        assert library == run.library
        assert request.transcript is None
        return MagicMock(draft=draft)

    save = MagicMock(return_value=MagicMock(model_dump=lambda **_kwargs: {"id": "clone-english"}))
    monkeypatch.setattr(qualification, "prepare_clone_review", review)
    monkeypatch.setattr(qualification, "clone_reference_voice", save)
    assert run.clone() == "clone-english"
    assert save.call_args.kwargs["transcript"] == "Observed audio words."
    assert save.call_args.kwargs["overwrite"] is False
    assert save.call_args.kwargs["library"] == run.library
