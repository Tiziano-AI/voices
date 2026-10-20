"""Persistence owner for render output artifacts."""

import fcntl
import json
import os
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
from pydantic import ValidationError

from voices.domain.contracts import OutputDraft, OutputRecord, require_voice_id, validate_output_artifact_name
from voices.domain.errors import InvalidInputError, InvalidOutputEntryError, VoiceNotFoundError, VoicesError
from voices.store.library_store import write_wav
from voices.util.slug import slugify
from voices.util.timestamps import utc_now_compact

OUTPUT_LOCK_NAME = ".render.lock"


@dataclass(frozen=True, slots=True)
class OutputArtifact:
    """Resolved persisted files for one rendered output sidecar."""

    record: OutputRecord
    wav_path: Path
    sidecar_path: Path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Persist deterministic JSON with UTF-8 encoding."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _output_root(out_dir: Path) -> Path:
    """Resolve the canonical output root and reject symlinked roots."""
    if out_dir.is_symlink():
        raise InvalidInputError("Output root must not be a symlink.")
    if out_dir.exists() and not out_dir.is_dir():
        raise InvalidInputError("Output root must be a directory.")
    return out_dir.expanduser().resolve(strict=False)


def _output_directory(out_dir: Path, voice_id: str) -> Path:
    """Resolve the output directory that owns one voice id."""
    validated_voice_id = require_voice_id(voice_id)
    resolved_root = _output_root(out_dir)
    candidate = resolved_root / validated_voice_id
    if candidate.parent != resolved_root:
        raise InvalidInputError(f"output voice id '{voice_id}' resolves outside the root")
    if candidate.is_symlink():
        raise InvalidInputError(f"output voice id '{voice_id}' must not be a symlink")
    if candidate.exists() and not candidate.is_dir():
        raise InvalidInputError(f"output voice id '{voice_id}' path must be a directory")
    return candidate


def _render_artifact_path_occupied(path: Path) -> bool:
    """Return whether one public render path is occupied, rejecting symlink occupants."""
    if path.is_symlink():
        raise InvalidInputError("Output artifact path must not be a symlink.")
    return path.exists()


def _validated_artifact_name(filename_or_path: str) -> str:
    """Return the canonical artifact basename from a CLI/path input or fail closed."""
    requested_name = Path(filename_or_path).name
    try:
        return validate_output_artifact_name(requested_name)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc


def _reserve_output_paths(target_directory: Path, text: str) -> tuple[Path, Path, Path, Path]:
    """Reserve one visible render basename plus hidden staging file paths."""
    timestamp = utc_now_compact()
    slug = slugify(text, max_length=40)
    base_name = f"{timestamp}__{slug}" if slug else timestamp
    suffix = 1
    wav_path = target_directory / f"{base_name}.wav"
    sidecar_path = target_directory / f"{wav_path.stem}.json"
    while _render_artifact_path_occupied(wav_path) or _render_artifact_path_occupied(sidecar_path):
        suffix += 1
        wav_path = target_directory / f"{base_name}-{suffix}.wav"
        sidecar_path = target_directory / f"{wav_path.stem}.json"
    staging_stem = f".{wav_path.stem}-staging-{uuid4().hex}"
    staging_wav_path = target_directory / f"{staging_stem}.wav"
    staging_sidecar_path = target_directory / f"{staging_stem}.json"
    return wav_path, sidecar_path, staging_wav_path, staging_sidecar_path


def _cleanup_staging_file(path: Path) -> None:
    """Remove one staged file when it still exists."""
    if path.exists():
        path.unlink()


@contextmanager
def _locked_output_directory(target_directory: Path) -> Iterator[Path]:
    """Hold the per-voice output publish lock for one output directory."""
    lock_path = target_directory / OUTPUT_LOCK_NAME
    open_flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    try:
        lock_fd = os.open(lock_path, open_flags, 0o600)
    except OSError as exc:
        if lock_path.is_symlink():
            raise InvalidInputError("Output lock file must not be a symlink.") from exc
        raise
    with os.fdopen(lock_fd, "a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield target_directory
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def save_rendered_output(
    out_dir: Path,
    output_draft: OutputDraft,
    audio_data: np.ndarray,
    sample_rate: int,
) -> Path:
    """Persist one render WAV plus its schema v2 sidecar."""
    return _publish_output(out_dir, output_draft, lambda path: write_wav(path, audio_data, sample_rate))


def save_existing_output(out_dir: Path, output_draft: OutputDraft, wav_source: Path) -> Path:
    """Publish an already encoded preview without resynthesis or re-encoding."""
    return _publish_output(out_dir, output_draft, lambda path: shutil.copyfile(wav_source, path))


def _publish_output(out_dir: Path, output_draft: OutputDraft, write_audio: Callable[[Path], object]) -> Path:
    """Own one locked WAV/sidecar publication for generated or retained audio."""
    target_directory = _output_directory(out_dir, output_draft.voice_id)
    target_directory.mkdir(parents=True, exist_ok=True)
    with _locked_output_directory(target_directory):
        wav_path, sidecar_path, staging_wav_path, staging_sidecar_path = _reserve_output_paths(
            target_directory,
            output_draft.text,
        )
        try:
            write_audio(staging_wav_path)
            output_record = OutputRecord(
                schema_version=2,
                voice_id=output_draft.voice_id,
                created_at=output_draft.created_at,
                language=output_draft.language,
                base_model_id=output_draft.base_model_id,
                base_model_revision=output_draft.base_model_revision,
                runtime=output_draft.runtime,
                text=output_draft.text,
                output_audio=wav_path.name,
                reference_voice_id=output_draft.reference_voice_id,
                reference_sha256=output_draft.reference_sha256,
                reference_text_sha256=output_draft.reference_text_sha256,
            )
            _write_json(
                staging_sidecar_path,
                output_record.model_dump(mode="json"),
            )
            staging_wav_path.replace(wav_path)
            try:
                staging_sidecar_path.replace(sidecar_path)
            except OSError:
                if wav_path.exists():
                    wav_path.unlink()
                raise
        finally:
            _cleanup_staging_file(staging_wav_path)
            _cleanup_staging_file(staging_sidecar_path)
    return wav_path


def resolve_output_path(out_dir: Path, voice_id: str, filename: str) -> Path:
    """Resolve one persisted render artifact or fail closed."""
    target_directory = _output_directory(out_dir, voice_id)
    artifact_name = _validated_artifact_name(filename)
    raw_candidate = target_directory / artifact_name
    if raw_candidate.is_symlink():
        raise InvalidInputError("Output file must not be a symlink")
    candidate = raw_candidate.resolve(strict=False)
    if candidate.parent != target_directory:
        raise InvalidInputError("Output file resolves outside the output directory")
    if not candidate.is_file():
        raise VoiceNotFoundError(f"Output '{filename}' for voice '{voice_id}' not found.")
    return candidate


def _load_output_record(sidecar_path: Path) -> OutputRecord:
    """Load one output sidecar and validate its persisted schema."""
    try:
        return OutputRecord.model_validate_json(sidecar_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InvalidOutputEntryError(f"Output sidecar '{sidecar_path.name}' cannot be read: {exc}") from exc
    except ValidationError as exc:
        message = f"Output sidecar '{sidecar_path.name}' is not a schema v2 output record."
        raise InvalidOutputEntryError(message) from exc


def output_artifact_for_sidecar(out_dir: Path, voice_id: str, sidecar_name: str) -> OutputArtifact:
    """Load one output artifact from its sidecar filename."""
    sidecar_path = resolve_output_path(out_dir, voice_id, sidecar_name)
    if sidecar_path.suffix != ".json":
        raise InvalidInputError("Output sidecar lookup requires a .json filename.")
    record = _load_output_record(sidecar_path)
    if record.voice_id != voice_id:
        raise InvalidOutputEntryError(f"Output sidecar '{sidecar_path.name}' voice id does not match its directory.")
    expected_sidecar_name = Path(record.output_audio).with_suffix(".json").name
    if sidecar_path.name != expected_sidecar_name:
        raise InvalidOutputEntryError(f"Output sidecar '{sidecar_path.name}' does not match output_audio.")
    wav_path = resolve_output_path(out_dir, voice_id, record.output_audio)
    return OutputArtifact(record=record, wav_path=wav_path, sidecar_path=sidecar_path)


def output_artifact_for_name(out_dir: Path, voice_id: str, filename_or_path: str) -> OutputArtifact:
    """Load one output artifact from a WAV or sidecar filename."""
    requested_path = Path(filename_or_path)
    if requested_path.suffix == ".wav":
        sidecar_name = f"{requested_path.stem}.json"
    elif requested_path.suffix == ".json":
        sidecar_name = requested_path.name
    else:
        raise InvalidInputError("Output lookup requires a .wav or .json filename.")
    return output_artifact_for_sidecar(out_dir, voice_id, sidecar_name)


def list_output_artifacts(out_dir: Path, voice_id: str) -> list[OutputArtifact]:
    """Return persisted render artifacts for one voice, newest first."""
    target_directory = _output_directory(out_dir, voice_id)
    if not target_directory.is_dir():
        return []
    artifacts: list[OutputArtifact] = []
    issues: list[str] = []
    for sidecar_path in sorted(target_directory.glob("*.json")):
        if sidecar_path.name.startswith("."):
            continue
        try:
            artifacts.append(output_artifact_for_sidecar(out_dir, voice_id, sidecar_path.name))
        except VoicesError as exc:
            issues.append(str(exc))
    if issues:
        issue_list = "\n".join(f"- {issue}" for issue in issues)
        raise InvalidOutputEntryError(f"Output directory '{target_directory}' contains invalid entries:\n{issue_list}")
    artifacts.sort(key=lambda artifact: (artifact.record.created_at, artifact.sidecar_path.name), reverse=True)
    return artifacts
