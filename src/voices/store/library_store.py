"""Canonical persistence owner for saved voices and render artifacts."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
import wave
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import numpy as np
from pydantic import TypeAdapter, ValidationError

from voices.domain.contracts import VoiceDraft, VoiceRecord, require_voice_id
from voices.domain.errors import (
    InvalidInputError,
    InvalidVoiceEntryError,
    LibraryIntegrityError,
    VoiceAlreadyExistsError,
    VoiceNotFoundError,
    VoicesError,
)
from voices.util.hashing import sha256_file

REFERENCE_AUDIO_NAME = "reference.wav"
REFERENCE_TEXT_NAME = "reference.txt"
VOICE_METADATA_NAME = "voice.json"
JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, object])


@dataclass(frozen=True, slots=True)
class VoiceSnapshot:
    """One operation-owned, coherent reference captured before runtime admission."""

    record: VoiceRecord
    reference_audio: bytes

    @property
    def reference_text(self) -> str:
        """Return the validated transcript from this same capture."""
        return self.record.reference_text

    @property
    def reference_text_sha256(self) -> str:
        """Identify the transcript paired with these WAV bytes."""
        return self.record.reference_text_sha256


def write_wav(path: Path, audio_data: np.ndarray, sample_rate: int) -> None:
    """Write mono float32 audio as 16-bit PCM WAV."""
    clamped = np.clip(audio_data, -1.0, 1.0)
    pcm = (clamped * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _write_text(path: Path, text: str) -> None:
    """Persist UTF-8 text with no extra serialization layer."""
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Persist deterministic JSON with UTF-8 encoding."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json(data: bytes, voice_id: str) -> dict[str, object]:
    """Load a JSON object from disk."""
    try:
        payload_object: object = json.loads(data)
    except json.JSONDecodeError as exc:
        raise InvalidVoiceEntryError(f"Voice '{voice_id}' contains malformed JSON: {exc}") from exc
    try:
        return JSON_OBJECT_ADAPTER.validate_python(payload_object)
    except ValidationError as exc:
        raise InvalidVoiceEntryError(f"Voice '{voice_id}' does not contain a JSON object.") from exc


def _directory_within_root(root: Path, voice_id: str, *, label: str) -> Path:
    """Resolve one validated voice-owned directory under a canonical root."""
    validated_voice_id = require_voice_id(voice_id)
    resolved_root = root.resolve(strict=False)
    candidate = resolved_root / validated_voice_id
    if candidate.parent != resolved_root:
        raise InvalidInputError(f"{label} '{voice_id}' resolves outside the root")
    if candidate.is_symlink():
        raise InvalidInputError(f"{label} '{voice_id}' must not be a symlink")
    return candidate


def _voice_directory(library: Path, voice_id: str) -> Path:
    """Resolve the directory that owns one voice id."""
    return _directory_within_root(library, voice_id, label="voice id")


def _staging_directory(parent_directory: Path, *, prefix: str) -> Path:
    """Create one hidden same-parent staging directory."""
    parent_directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent_directory))


def _finalized_voice_record(voice_draft: VoiceDraft, reference_audio_path: Path) -> VoiceRecord:
    """Build one persisted voice record after the reference audio digest is known."""
    return VoiceRecord(
        schema_version=2,
        id=voice_draft.id,
        name=voice_draft.name,
        created_at=voice_draft.created_at,
        language=voice_draft.language,
        base_model_id=voice_draft.base_model_id,
        reference_text=voice_draft.reference_text,
        reference_sha256=sha256_file(reference_audio_path),
        source=voice_draft.source,
    )


def _write_voice_directory(
    voice_directory: Path,
    voice_draft: VoiceDraft,
    audio_data: np.ndarray,
    sample_rate: int,
) -> VoiceRecord:
    """Write one complete voice directory in place and return its finalized record."""
    reference_audio_path = voice_directory / REFERENCE_AUDIO_NAME
    write_wav(reference_audio_path, audio_data, sample_rate)
    _write_text(voice_directory / REFERENCE_TEXT_NAME, voice_draft.reference_text)
    finalized_record = _finalized_voice_record(voice_draft, reference_audio_path)
    _write_json(
        voice_directory / VOICE_METADATA_NAME,
        finalized_record.model_dump(mode="json"),
    )
    return finalized_record


def _restore_backup_voice_directory(backup_directory: Path, voice_directory: Path) -> None:
    """Restore one previous saved voice after a failed staged publish."""
    try:
        backup_directory.replace(voice_directory)
    except OSError as restore_error:
        raise OSError(
            f"Failed to publish staged voice '{voice_directory.name}' and failed to restore the previous saved voice."
        ) from restore_error


def _publish_staged_voice_directory(staging_directory: Path, voice_directory: Path, *, overwrite: bool) -> None:
    """Swap one staged voice directory into the canonical library path."""
    if voice_directory.is_symlink():
        raise InvalidInputError(f"Voice '{voice_directory.name}' must not be a symlink.")
    if voice_directory.exists() and not voice_directory.is_dir():
        raise InvalidInputError(f"Voice '{voice_directory.name}' path must be a directory.")
    if not overwrite:
        try:
            staging_directory.rename(voice_directory)
        except OSError as exc:
            if voice_directory.exists() or voice_directory.is_symlink():
                raise VoiceAlreadyExistsError(
                    f"Voice '{voice_directory.name}' already exists. Use --overwrite to replace."
                ) from exc
            raise
        return
    backup_directory: Path | None = None
    if voice_directory.exists():
        backup_directory = voice_directory.parent / f".{voice_directory.name}-backup-{uuid4().hex}"
        voice_directory.replace(backup_directory)
    try:
        staging_directory.replace(voice_directory)
    except OSError:
        if backup_directory is not None and backup_directory.exists():
            _restore_backup_voice_directory(backup_directory, voice_directory)
        raise
    if backup_directory is not None and backup_directory.exists():
        shutil.rmtree(backup_directory)


def _cleanup_directory(path: Path) -> None:
    """Remove one temp directory when it still exists."""
    if path.exists():
        shutil.rmtree(path)


def voice_exists(library: Path, voice_id: str) -> bool:
    """Return whether the requested voice directory already exists."""
    voice_directory = _voice_directory(library, voice_id)
    if voice_directory.exists() and not voice_directory.is_dir():
        raise InvalidInputError(f"Voice '{voice_id}' path must be a directory.")
    return voice_directory.is_dir()


def save_voice_record(
    library: Path,
    voice_draft: VoiceDraft,
    audio_data: np.ndarray,
    sample_rate: int,
    overwrite: bool = False,
) -> VoiceRecord:
    """Persist one reference voice and return the finalized record."""
    voice_directory = _voice_directory(library, voice_draft.id)
    if voice_directory.exists() and not voice_directory.is_dir():
        raise InvalidInputError(f"Voice '{voice_draft.id}' path must be a directory.")
    if voice_directory.exists() and not overwrite:
        raise VoiceAlreadyExistsError(f"Voice '{voice_draft.id}' already exists. Use --overwrite to replace.")
    staging_directory = _staging_directory(voice_directory.parent, prefix=f".{voice_draft.id}-staging-")
    try:
        finalized_record = _write_voice_directory(staging_directory, voice_draft, audio_data, sample_rate)
        _publish_staged_voice_directory(staging_directory, voice_directory, overwrite=overwrite)
    except OSError, ValidationError, VoicesError:
        _cleanup_directory(staging_directory)
        raise
    return finalized_record


def load_voice_record(library: Path, voice_id: str) -> VoiceRecord:
    """Load and fully validate one saved voice."""
    return load_voice_snapshot(library, voice_id).record


def _open_voice_asset(directory_fd: int, name: str, voice_id: str) -> BinaryIO:
    """Open a regular asset relative to the captured directory, never following links."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except OSError as exc:
        raise InvalidVoiceEntryError(
            f"Voice '{voice_id}' {name} must be a readable regular file, not a symlink; "
            "the reference may have changed during capture."
        ) from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise InvalidVoiceEntryError(f"Voice '{voice_id}' {name} must be a regular file.")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def load_voice_snapshot(library: Path, voice_id: str) -> VoiceSnapshot:
    """Read one anchored asset set, or fail before synthesis if an overwrite retires it."""
    voice_directory = _voice_directory(library, voice_id)
    try:
        directory_fd = os.open(voice_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError, NotADirectoryError:
        raise VoiceNotFoundError(f"Voice '{voice_id}' not found.") from None
    with ExitStack() as stack:
        stack.callback(os.close, directory_fd)
        # Open every asset before reading: replacement may unlink the old directory,
        # but these descriptors continue to own the same complete reference.
        handles = [
            stack.enter_context(_open_voice_asset(directory_fd, name, voice_id))
            for name in (VOICE_METADATA_NAME, REFERENCE_AUDIO_NAME, REFERENCE_TEXT_NAME)
        ]
        metadata, audio, transcript = (handle.read() for handle in handles)
    try:
        record = VoiceRecord.model_validate(_read_json(metadata, voice_id))
        reference_text = transcript.decode("utf-8").rstrip()
    except (ValidationError, UnicodeError) as exc:
        raise InvalidVoiceEntryError(f"Voice '{voice_id}' failed schema validation: {exc}") from exc
    if record.id != voice_id:
        raise InvalidVoiceEntryError(f"Voice '{voice_id}' metadata id does not match its directory name.")
    if record.reference_text != reference_text:
        raise InvalidVoiceEntryError(f"Voice '{voice_id}' metadata and reference transcript disagree.")
    if record.reference_sha256 != hashlib.sha256(audio).hexdigest():
        raise InvalidVoiceEntryError(f"Voice '{voice_id}' metadata and reference audio digest disagree.")
    return VoiceSnapshot(record=record, reference_audio=audio)


def list_voice_records(library: Path) -> list[VoiceRecord]:
    """Return the complete validated voice library or fail closed on corruption."""
    if not library.is_dir():
        return []
    records: list[tuple[VoiceRecord, int]] = []
    issues: list[str] = []
    for child in sorted(library.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_symlink():
            issues.append(f"Voice '{child.name}' directory must not be a symlink.")
            continue
        if not child.is_dir():
            issues.append(f"Voice '{child.name}' entry must be a directory.")
            continue
        try:
            record = load_voice_record(library, child.name)
            records.append((record, (child / VOICE_METADATA_NAME).stat().st_mtime_ns))
        except (InvalidInputError, InvalidVoiceEntryError) as exc:
            issues.append(str(exc))
        except OSError as exc:
            issues.append(f"Voice '{child.name}' metadata cannot be inspected: {exc}")
    if issues:
        issue_list = "\n".join(f"- {issue}" for issue in issues)
        raise LibraryIntegrityError(f"Voice library '{library}' contains invalid entries:\n{issue_list}")
    records.sort(key=lambda item: (item[0].created_at, item[1], item[0].id))
    return [record for record, _metadata_mtime in records]


def delete_voice_record(library: Path, voice_id: str) -> None:
    """Delete one saved voice directory."""
    voice_directory = _voice_directory(library, voice_id)
    if not voice_directory.is_dir():
        raise VoiceNotFoundError(f"Voice '{voice_id}' not found.")
    shutil.rmtree(voice_directory)
