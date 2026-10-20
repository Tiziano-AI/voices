"""CLI commands for explicit clone review and save phases."""

import json
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from voices import config
from voices.cli_json import context_from_typer, emit_json, model_object, run_cli_action
from voices.cli_support import console, default_display_name, resolve_optional_name
from voices.config import get_library_path
from voices.domain.contracts import require_non_empty_text, require_supported_language, require_voice_id
from voices.domain.create_contracts import CloneReviewRequest, TranscriptionSegment
from voices.domain.errors import InvalidInputError, InvalidPromptFileError
from voices.store.library_store import write_wav
from voices.workflow.clone_voice import clone_reference_voice, prepare_clone_review

clone_app = typer.Typer(help="Review and save imported reference voices.")


class CloneReviewFile(BaseModel):
    """Durable CLI review handoff between `clone review` and `clone save`."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    audio_path: str
    suggested_voice_id: str
    transcript: str
    language: str
    duration_seconds: float
    segments: list[TranscriptionSegment]
    review_policy: Literal["import"] = "import"

    @field_validator("audio_path", "transcript")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """Reject blank review fields."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("review field must not be empty")
        return normalized

    @field_validator("suggested_voice_id")
    @classmethod
    def validate_suggested_voice_id(cls, value: str) -> str:
        """Validate the suggested voice id saved in the review file."""
        return require_voice_id(value)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        """Validate the language saved in the review file."""
        return require_supported_language(value)


def _review_payload(review_file: CloneReviewFile, review_path: Path) -> dict[str, object]:
    """Project one review file into the CLI JSON output contract."""
    return {
        "review": model_object(review_file),
        "paths": {
            "review": str(review_path),
            "audio": review_file.audio_path,
        },
    }


def _prepare_review_paths(review_out: Path) -> tuple[Path, Path]:
    """Resolve and reserve one review JSON path plus its WAV sibling."""
    review_path = review_out.expanduser().resolve(strict=False)
    if review_path.suffix != ".json":
        raise InvalidInputError("--review-out must end with .json.")
    audio_path = review_path.with_suffix(".wav")
    if review_path.exists() or audio_path.exists():
        raise InvalidInputError("Review output paths already exist.")
    review_path.parent.mkdir(parents=True, exist_ok=True)
    return review_path, audio_path


def _write_review_file(review_path: Path, review_file: CloneReviewFile) -> None:
    """Persist one clone review file without silently replacing prior artifacts."""
    review_path.write_text(
        json.dumps(model_object(review_file), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_review_file(review_path: Path) -> CloneReviewFile:
    """Load and validate one clone review handoff file."""
    try:
        return CloneReviewFile.model_validate_json(review_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InvalidPromptFileError(f"Unable to read review file '{review_path}': {exc}") from exc
    except ValidationError as exc:
        raise InvalidPromptFileError(f"Review file '{review_path}' failed schema validation: {exc}") from exc


@clone_app.command("review")
def review_clone(
    ctx: typer.Context,
    audio: Annotated[Path, typer.Option("--audio", help="Audio file to clone from.")],
    review_out: Annotated[Path, typer.Option("--review-out", help="JSON review file to write.")],
    transcript: Annotated[
        str | None,
        typer.Option("--transcript", help="Approved transcript. When omitted, local STT creates the draft."),
    ] = None,
    name: Annotated[str | None, typer.Option("--name", help="Display name used for id suggestion.")] = None,
    voice_id: Annotated[str | None, typer.Option("--voice-id", help="Requested voice id for suggestion.")] = None,
    language: Annotated[
        str,
        typer.Option("--language", help="Language for transcript review and saved metadata."),
    ] = config.DEFAULT_LANGUAGE,
    library: Annotated[Path | None, typer.Option("--library", help="Voice library directory.")] = None,
) -> None:
    """Create a durable clone review draft from imported audio."""
    context = context_from_typer(ctx)

    def run() -> None:
        if not audio.exists():
            raise InvalidInputError(f"Audio file not found: {audio}")
        lib = get_library_path(library)
        resolved_language = require_supported_language(language)
        resolved_name = resolve_optional_name(name)
        resolved_voice_id = require_voice_id(voice_id) if voice_id is not None else None
        resolved_transcript = require_non_empty_text("transcript", transcript) if transcript is not None else None
        fallback_name = resolved_name or default_display_name(audio.stem)
        prepared = prepare_clone_review(
            audio_path=audio,
            library=lib,
            request=CloneReviewRequest(
                language=resolved_language,
                review_policy="import",
                transcript=resolved_transcript,
                requested_name=resolved_name,
                requested_voice_id=resolved_voice_id,
                fallback_name=fallback_name,
            ),
        )
        review_path, review_audio_path = _prepare_review_paths(review_out)
        review_file = CloneReviewFile(
            audio_path=str(review_audio_path),
            suggested_voice_id=prepared.suggested_voice_id,
            transcript=prepared.draft.transcript,
            language=prepared.draft.language,
            duration_seconds=prepared.draft.duration_seconds,
            segments=prepared.draft.segments,
        )
        write_wav(review_audio_path, prepared.normalized_audio, config.FALLBACK_SAMPLE_RATE)
        try:
            _write_review_file(review_path, review_file)
        except OSError as exc:
            review_audio_path.unlink(missing_ok=True)
            raise InvalidInputError(f"Unable to write review file '{review_path}': {exc}") from exc
        if context.json_output:
            emit_json(_review_payload(review_file, review_path))
            return
        console.print(f"[green]Review:[/] {review_path}")
        console.print(f"[green]Audio:[/] {review_audio_path}")
        console.print(f"[green]Suggested voice:[/] {review_file.suggested_voice_id}")

    run_cli_action(context, run)


@clone_app.command("save")
def save_clone(
    ctx: typer.Context,
    review: Annotated[Path, typer.Option("--review", help="Review JSON produced by clone review.")],
    id: Annotated[str, typer.Option("--id", help="Voice identifier.")],
    name: Annotated[str, typer.Option("--name", help="Display name.")],
    library: Annotated[Path | None, typer.Option("--library", help="Voice library directory.")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing voice.")] = False,
) -> None:
    """Persist one reviewed clone voice."""
    context = context_from_typer(ctx)

    def run() -> None:
        review_file = _load_review_file(review.expanduser())
        resolved_id = require_voice_id(id)
        resolved_name = resolve_optional_name(name)
        if resolved_name is None:
            raise InvalidInputError("voice name must not be empty")
        lib = get_library_path(library)
        record = clone_reference_voice(
            voice_id=resolved_id,
            name=resolved_name,
            audio_path=Path(review_file.audio_path),
            transcript=review_file.transcript,
            language=review_file.language,
            library=lib,
            overwrite=overwrite,
        )
        payload: dict[str, object] = {
            "voice": model_object(record),
            "paths": {
                "voice": str(lib / record.id),
                "reference_audio": str(lib / record.id / "reference.wav"),
                "metadata": str(lib / record.id / "voice.json"),
            },
        }
        if context.json_output:
            emit_json(payload)
            return
        console.print(f"[green]Cloned voice:[/] {record.id} → {lib / record.id}")

    run_cli_action(context, run)
