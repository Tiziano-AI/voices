from threading import Event, Thread
from unittest.mock import patch

import pytest
from helpers import MOCK_AUDIO, seed_clone_voice

from voices.domain.errors import VoiceAlreadyExistsError, VoiceNotFoundError
from voices.edge.contracts import CloneSaveRequest
from voices.edge.service import StudioContext, save_clone_from_review
from voices.edge.storage import StudioAssetStore


def test_review_token_allows_only_one_concurrent_save(tmp_path):
    library = tmp_path / "voices"
    context = StudioContext(
        library=library,
        out_dir=tmp_path / "outputs",
        asset_store=StudioAssetStore(),
    )
    review_session = context.asset_store.save_review_audio(MOCK_AUDIO, "English", "stage-voice")
    clone_started = Event()
    release_clone = Event()
    outcomes: list[str] = []

    def blocked_clone_reference_voice(
        *,
        voice_id: str,
        name: str | None,
        audio_path,
        transcript: str,
        language: str,
        library,
        overwrite: bool,
    ):
        del name, audio_path, transcript, language, overwrite
        clone_started.set()
        assert release_clone.wait(5)
        return seed_clone_voice(library, voice_id)

    def save_voice(request: CloneSaveRequest) -> None:
        try:
            detail = save_clone_from_review(context, request)
        except VoiceNotFoundError:
            outcomes.append("missing")
            return
        outcomes.append(f"ok:{detail.record.id}")

    first_request = CloneSaveRequest(
        review_token=review_session.review_token,
        voice_id="voice_a",
        name="Voice A",
        transcript="Approved transcript.",
        overwrite=False,
    )
    second_request = CloneSaveRequest(
        review_token=review_session.review_token,
        voice_id="voice_b",
        name="Voice B",
        transcript="Approved transcript.",
        overwrite=False,
    )

    with patch("voices.edge.service.clone_reference_voice", side_effect=blocked_clone_reference_voice):
        first_thread = Thread(target=save_voice, args=(first_request,))
        first_thread.start()
        assert clone_started.wait(5)

        second_thread = Thread(target=save_voice, args=(second_request,))
        second_thread.start()
        second_thread.join()

        release_clone.set()
        first_thread.join()

    assert sorted(outcomes) == ["missing", "ok:voice_a"]
    assert (library / "voice_a" / "voice.json").exists()
    assert not (library / "voice_b").exists()


def test_failed_clone_save_releases_review_claim(tmp_path):
    library = tmp_path / "voices"
    context = StudioContext(
        library=library,
        out_dir=tmp_path / "outputs",
        asset_store=StudioAssetStore(),
    )
    review_session = context.asset_store.save_review_audio(MOCK_AUDIO, "English", "stage-voice")
    call_count = 0

    def flaky_clone_reference_voice(
        *,
        voice_id: str,
        name: str | None,
        audio_path,
        transcript: str,
        language: str,
        library,
        overwrite: bool,
    ):
        nonlocal call_count
        del name, audio_path, transcript, language, overwrite
        call_count += 1
        if call_count == 1:
            raise VoiceAlreadyExistsError("Voice 'occupied' already exists. Use --overwrite to replace.")
        return seed_clone_voice(library, voice_id)

    with patch("voices.edge.service.clone_reference_voice", side_effect=flaky_clone_reference_voice):
        with pytest.raises(VoiceAlreadyExistsError, match="occupied"):
            save_clone_from_review(
                context,
                CloneSaveRequest(
                    review_token=review_session.review_token,
                    voice_id="occupied",
                    name="Occupied",
                    transcript="Approved transcript.",
                    overwrite=False,
                ),
            )

        detail = save_clone_from_review(
            context,
            CloneSaveRequest(
                review_token=review_session.review_token,
                voice_id="recovered_voice",
                name="Recovered Voice",
                transcript="Approved transcript.",
                overwrite=False,
            ),
        )

    assert detail.record.id == "recovered_voice"
    assert (library / "recovered_voice" / "voice.json").exists()
