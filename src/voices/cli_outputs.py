"""CLI commands for inspecting persisted render outputs."""

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from voices.cli_json import (
    collection_payload,
    context_from_typer,
    emit_json,
    model_object,
    require_limit,
    run_cli_action,
)
from voices.cli_support import console
from voices.config import DEFAULT_OUTPUT_DIR
from voices.store.output_store import OutputArtifact, list_output_artifacts, output_artifact_for_name

outputs_app = typer.Typer(help="Inspect persisted render output artifacts.")


def _artifact_payload(artifact: OutputArtifact) -> dict[str, object]:
    """Project one output artifact into the canonical CLI JSON shape."""
    return {
        "artifact": model_object(artifact.record),
        "paths": {
            "wav": str(artifact.wav_path),
            "sidecar": str(artifact.sidecar_path),
        },
    }


def _artifact_item(artifact: OutputArtifact) -> dict[str, object]:
    """Project one output artifact for collection reads."""
    return {
        "voice_id": artifact.record.voice_id,
        "created_at": artifact.record.created_at,
        "language": artifact.record.language,
        "text": artifact.record.text,
        "output_audio": artifact.record.output_audio,
        "wav_path": str(artifact.wav_path),
        "sidecar_path": str(artifact.sidecar_path),
    }


def _render_outputs_table(artifacts: list[OutputArtifact]) -> Table:
    """Build the human table for persisted render artifacts."""
    table = Table(title="Outputs", expand=True)
    table.add_column("created", no_wrap=True)
    table.add_column("voice", no_wrap=True)
    table.add_column("audio", no_wrap=True)
    table.add_column("text", overflow="fold", ratio=1)
    for artifact in artifacts:
        table.add_row(
            artifact.record.created_at,
            artifact.record.voice_id,
            artifact.record.output_audio,
            artifact.record.text,
        )
    return table


@outputs_app.command("list")
def list_outputs(
    ctx: typer.Context,
    voice: Annotated[str, typer.Option("--voice", help="Voice ID whose outputs should be listed.")],
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum output artifacts to return.")] = None,
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory.")] = DEFAULT_OUTPUT_DIR,
) -> None:
    """List persisted render artifacts for one voice."""
    context = context_from_typer(ctx)

    def run() -> None:
        resolved_limit = require_limit(limit)
        artifacts = list_output_artifacts(out_dir, voice)
        limited_artifacts = artifacts[:resolved_limit] if resolved_limit is not None else artifacts
        if context.json_output:
            emit_json(collection_payload([_artifact_item(artifact) for artifact in limited_artifacts], resolved_limit))
            return
        if not limited_artifacts:
            console.print("[dim]No outputs found for this voice.[/]")
            return
        console.print(_render_outputs_table(limited_artifacts))

    run_cli_action(context, run)


@outputs_app.command("show")
def show_output(
    ctx: typer.Context,
    voice_id: Annotated[str, typer.Argument(help="Voice identifier.")],
    filename_or_path: Annotated[str, typer.Argument(help="WAV or JSON sidecar filename.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory.")] = DEFAULT_OUTPUT_DIR,
) -> None:
    """Show one persisted render artifact."""
    context = context_from_typer(ctx)

    def run() -> None:
        artifact = output_artifact_for_name(out_dir, voice_id, filename_or_path)
        if context.json_output:
            emit_json(_artifact_payload(artifact))
            return
        payload = model_object(artifact.record)
        table = Table(show_header=False, box=None, pad_edge=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        for key, value in payload.items():
            table.add_row(key, str(value))
        table.add_row("wav_path", str(artifact.wav_path))
        table.add_row("sidecar_path", str(artifact.sidecar_path))
        console.print(table)

    run_cli_action(context, run)
