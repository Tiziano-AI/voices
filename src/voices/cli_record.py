"""CLI commands for microphone recording and recording plans."""

import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from voices import config
from voices.cli_json import context_from_typer, emit_json, run_cli_action
from voices.cli_review import prompt_non_empty, record_and_review
from voices.cli_support import console, default_display_name, resolve_optional_name
from voices.config import get_library_path
from voices.domain.contracts import require_supported_language, require_voice_id
from voices.domain.create_contracts import get_guided_recording_script
from voices.domain.errors import InvalidInputError, VoiceAlreadyExistsError
from voices.store.library_store import voice_exists
from voices.util.slug import voice_id_from_name
from voices.workflow.clone_voice import clone_reference_voice, suggest_voice_id

record_app = typer.Typer(help="Record microphone audio and inspect recording constraints.")


def _resolve_record_identity(
    library: Path,
    requested_id: str | None,
    requested_name: str | None,
    *,
    overwrite: bool,
) -> tuple[str, str]:
    """Resolve the saved clone identity for one recorded voice."""
    if requested_id is not None:
        return requested_id, requested_name or default_display_name(requested_id)
    if requested_name is not None:
        if overwrite:
            return voice_id_from_name(requested_name), requested_name
        return suggest_voice_id(library, requested_name), requested_name
    name = prompt_non_empty("Voice name", "My Voice")
    if overwrite:
        return voice_id_from_name(name), name
    return suggest_voice_id(library, name), name


def _require_record_mode(mode: str) -> str:
    """Validate one public recording mode."""
    resolved_mode = mode.strip().lower()
    if resolved_mode not in {"guided", "free"}:
        raise InvalidInputError("--mode must be 'guided' or 'free'.")
    return resolved_mode


def _record_plan_payload(mode: str, language: str, script: str | None) -> dict[str, object]:
    """Build the non-interactive recording plan payload."""
    resolved_mode = _require_record_mode(mode)
    resolved_language = require_supported_language(language)
    if resolved_mode == "guided":
        resolved_script = script or get_guided_recording_script(resolved_language)
        return {
            "mode": resolved_mode,
            "language": resolved_language,
            "script": resolved_script,
            "target_seconds": config.GUIDED_RECORD_TARGET_SECONDS,
            "minimum_seconds": None,
            "stop_rule": "auto_stop_after_target_seconds",
            "ffmpeg_required": True,
        }
    return {
        "mode": resolved_mode,
        "language": resolved_language,
        "script": script,
        "target_seconds": None,
        "minimum_seconds": config.FREE_RECORD_MINIMUM_SECONDS,
        "stop_rule": "operator_stops_recording",
        "ffmpeg_required": True,
    }


def _render_record_plan_table(payload: dict[str, object]) -> Table:
    """Build the human table for one recording plan."""
    table = Table(title="Recording Plan", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", overflow="fold")
    for key, value in payload.items():
        table.add_row(key, str(value))
    return table


@record_app.callback(invoke_without_command=True)
def record(
    ctx: typer.Context,
    id: Annotated[str | None, typer.Option("--id", help="Voice identifier. Derived from name when omitted.")] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Display name. Prompted when both --id and --name are omitted."),
    ] = None,
    mode: Annotated[str, typer.Option("--mode", help="Recording mode: guided or free.")] = "guided",
    script: Annotated[str | None, typer.Option("--script", help="Guided script override.")] = None,
    language: Annotated[
        str,
        typer.Option("--language", help="Language for capture script, transcript review, and saved metadata."),
    ] = config.DEFAULT_LANGUAGE,
    library: Annotated[Path | None, typer.Option("--library", help="Voice library directory.")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing voice.")] = False,
) -> None:
    """Record a reference voice from your microphone and save it as a clone."""
    if ctx.invoked_subcommand is not None:
        return
    context = context_from_typer(ctx)

    def run() -> None:
        if context.json_output:
            raise InvalidInputError("JSON mode supports 'record plan' only; microphone capture is interactive.")
        resolved_mode = _require_record_mode(mode)
        lib = get_library_path(library)
        resolved_language = require_supported_language(language)
        resolved_name = resolve_optional_name(name)
        if id is not None:
            resolved_requested_id = require_voice_id(id)
            if voice_exists(lib, resolved_requested_id) and not overwrite:
                raise VoiceAlreadyExistsError(
                    f"Voice '{resolved_requested_id}' already exists. Use --overwrite to replace."
                )
        with tempfile.TemporaryDirectory(prefix="voices-record-") as temp_dir_name:
            audio_path = Path(temp_dir_name) / "recording.wav"
            approved_transcript = record_and_review(audio_path, resolved_mode, resolved_language, script, lib)
            resolved_id, resolved_display_name = _resolve_record_identity(
                lib,
                id,
                resolved_name,
                overwrite=overwrite,
            )
            record_result = clone_reference_voice(
                voice_id=resolved_id,
                name=resolved_display_name,
                audio_path=audio_path,
                transcript=approved_transcript,
                language=resolved_language,
                library=lib,
                overwrite=overwrite,
            )
        console.print(f"[green]Recorded voice:[/] {record_result.id} → {lib / record_result.id}")

    run_cli_action(context, run)


@record_app.command("plan")
def plan_recording(
    ctx: typer.Context,
    mode: Annotated[str, typer.Option("--mode", help="Recording mode: guided or free.")] = "guided",
    script: Annotated[str | None, typer.Option("--script", help="Guided script override.")] = None,
    language: Annotated[str, typer.Option("--language", help="Recording language.")] = config.DEFAULT_LANGUAGE,
) -> None:
    """Show the recording script, timing, and stop rule without using the microphone."""
    context = context_from_typer(ctx)

    def run() -> None:
        payload = _record_plan_payload(mode, language, script)
        if context.json_output:
            emit_json(payload)
            return
        console.print(_render_record_plan_table(payload))

    run_cli_action(context, run)
