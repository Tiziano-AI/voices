import shutil
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from voices.config import FALLBACK_SAMPLE_RATE
from voices.domain.contracts import OutputDraft
from voices.domain.errors import PreviewStorageError, VoiceNotFoundError
from voices.store.library_store import write_wav
from voices.store.output_store import save_existing_output


@dataclass(frozen=True, slots=True)
class StoredAsset:
    """One ephemeral WAV file exposed through the local HTTP edge."""

    token: str
    path: Path


@dataclass(frozen=True, slots=True)
class ReviewSession:
    """One pending clone-save review session."""

    review_token: str
    audio_path: Path
    language: str
    suggested_voice_id: str


class ClaimedReviewSession:
    """Exclusive save claim for one pending clone-review session."""

    def __init__(self, store: "StudioAssetStore", session: ReviewSession) -> None:
        self._store = store
        self.session = session
        self._closed = False

    def __enter__(self) -> "ClaimedReviewSession":
        """Return the claimed session wrapper."""
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        """Release the claim unless the caller retires it explicitly."""
        if not self._closed:
            self.release()

    def release(self) -> None:
        """Release the claim so the review can be retried."""
        if self._closed:
            return
        self._store.release_review_session(self.session.review_token)
        self._closed = True

    def retire(self) -> None:
        """Consume the review session permanently after one successful save."""
        if self._closed:
            return
        self._store.discard_review_session(self.session.review_token)
        self._closed = True


class StudioAssetStore:
    """Own ephemeral preview and review assets for one edge server process."""

    def __init__(self) -> None:
        self._root = Path(tempfile.mkdtemp(prefix="voices-ui-"))
        self._asset_paths: dict[str, Path] = {}
        self._preview_drafts: dict[str, OutputDraft] = {}
        self._preview_exports: dict[str, Path] = {}
        self._review_sessions: dict[str, ReviewSession] = {}
        self._claimed_review_tokens: set[str] = set()
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        """Return the temp root for this edge process."""
        return self._root

    def cleanup(self) -> None:
        """Remove all temp assets for the current edge process."""
        with self._lock:
            self._asset_paths.clear()
            self._preview_drafts.clear()
            self._preview_exports.clear()
            self._review_sessions.clear()
            self._claimed_review_tokens.clear()
        if self._root.exists():
            shutil.rmtree(self._root)

    def save_preview_audio(self, audio_data: np.ndarray, sample_rate: int, output_draft: OutputDraft) -> StoredAsset:
        """Persist one synthesized preview clip and return its token."""
        token = uuid4().hex
        path = self._root / f"{token}.wav"
        try:
            write_wav(path, audio_data, sample_rate)
        except OSError as exc:
            with suppress(OSError):
                path.unlink(missing_ok=True)
            raise PreviewStorageError(
                f"Preview audio for voice '{output_draft.voice_id}' could not be saved: {exc.strerror or str(exc)}. "
                "Check disk space and temporary-folder permissions before retrying."
            ) from exc
        with self._lock:
            self._asset_paths[token] = path
            self._preview_drafts[token] = output_draft.model_copy(deep=True)
        return StoredAsset(token=token, path=path)

    def export_preview(self, token: str, out_dir: Path) -> Path:
        """Persist one exact preview occurrence once, retaining its original provenance."""
        with self._lock:
            draft = self._preview_drafts.get(token)
            audio_path = self._asset_paths.get(token)
            if draft is None or audio_path is None or not audio_path.is_file():
                raise VoiceNotFoundError("Preview expired or not found. Generate a new preview.")
            existing = self._preview_exports.get(token)
            if existing is not None:
                return existing
            exported = save_existing_output(out_dir, draft, audio_path)
            self._preview_exports[token] = exported
            return exported

    def save_review_audio(self, audio_data: np.ndarray, language: str, suggested_voice_id: str) -> ReviewSession:
        """Persist one normalized review clip and return its review session."""
        review_token = uuid4().hex
        audio_path = self._root / f"review-{review_token}.wav"
        write_wav(audio_path, audio_data, FALLBACK_SAMPLE_RATE)
        review_session = ReviewSession(
            review_token=review_token,
            audio_path=audio_path,
            language=language,
            suggested_voice_id=suggested_voice_id,
        )
        with self._lock:
            self._asset_paths[review_token] = audio_path
            self._review_sessions[review_token] = review_session
        return review_session

    def asset_path(self, token: str) -> Path:
        """Resolve one ephemeral asset path or fail closed."""
        with self._lock:
            path = self._asset_paths.get(token)
        if path is None or not path.exists():
            raise VoiceNotFoundError("Ephemeral audio asset not found.")
        return path

    def _review_session_unlocked(self, review_token: str) -> ReviewSession:
        """Resolve one review session while the store lock is held."""
        review_session = self._review_sessions.get(review_token)
        if review_session is None or not review_session.audio_path.exists():
            self._review_sessions.pop(review_token, None)
            self._asset_paths.pop(review_token, None)
            self._claimed_review_tokens.discard(review_token)
            raise VoiceNotFoundError("Review session not found.")
        return review_session

    def claim_review_session(self, review_token: str) -> ClaimedReviewSession:
        """Claim one pending review session for an exclusive save attempt."""
        with self._lock:
            review_session = self._review_session_unlocked(review_token)
            if review_token in self._claimed_review_tokens:
                raise VoiceNotFoundError("Review session not found.")
            self._claimed_review_tokens.add(review_token)
        return ClaimedReviewSession(self, review_session)

    def release_review_session(self, review_token: str) -> None:
        """Release an exclusive save claim without discarding the review session."""
        with self._lock:
            review_session = self._review_session_unlocked(review_token)
            self._claimed_review_tokens.discard(review_session.review_token)

    def discard_review_session(self, review_token: str) -> None:
        """Retire one review session and remove its temp audio."""
        with self._lock:
            review_session = self._review_session_unlocked(review_token)
            self._review_sessions.pop(review_token, None)
            self._asset_paths.pop(review_token, None)
            self._claimed_review_tokens.discard(review_token)
        if review_session.audio_path.exists():
            review_session.audio_path.unlink()
