"""Design creation commands for the voices CLI."""

from pathlib import Path
from typing import Annotated

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from voices.cli_json import collection_payload, context_from_typer, emit_json, model_object, run_cli_action
from voices.cli_support import (
    LibraryOption,
    console,
    default_display_name,
    err_console,
    resolve_optional_name,
)
from voices.config import DEFAULT_LANGUAGE, get_library_path
from voices.domain.contracts import require_non_empty_text, require_supported_language, require_voice_id
from voices.util.prompt_loader import load_prompts
from voices.workflow.design_voice import create_designed_voice, create_voice_batch

create_app = typer.Typer()


@create_app.command()
def design(
    ctx: typer.Context,
    id: Annotated[str, typer.Option("--id", help="Voice identifier.")],
    instruct: Annotated[str, typer.Option("--instruct", help="Voice design description.")],
    text: Annotated[str, typer.Option("--text", help="Seed text for reference audio.")],
    name: Annotated[str | None, typer.Option("--name", help="Display name.")] = None,
    language: Annotated[
        str,
        typer.Option("--language", help="Language for VoiceDesign generation."),
    ] = DEFAULT_LANGUAGE,
    library: LibraryOption = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing voice.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and preview without generating.")] = False,
) -> None:
    """Create a single voice from a design description."""
    context = context_from_typer(ctx)

    def run() -> None:
        lib = get_library_path(library)
        resolved_id = require_voice_id(id)
        resolved_language = require_supported_language(language)
        resolved_name = resolve_optional_name(name)
        resolved_instruct = require_non_empty_text("voice design prompt", instruct)
        resolved_text = require_non_empty_text("seed text", text)
        if dry_run:
            payload: dict[str, object] = {
                "voice": {
                    "id": resolved_id,
                    "name": resolved_name or default_display_name(resolved_id),
                    "language": resolved_language,
                    "source_kind": "design",
                    "description": resolved_instruct,
                    "reference_text": resolved_text,
                },
                "dry_run": True,
                "paths": {
                    "voice": str(lib / resolved_id),
                    "reference_audio": str(lib / resolved_id / "reference.wav"),
                    "metadata": str(lib / resolved_id / "voice.json"),
                },
            }
            if context.json_output:
                emit_json(payload)
                return
            table = Table(title="Dry Run — voice to create")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Language")
            table.add_column("Instruct", max_width=50)
            table.add_row(
                resolved_id,
                resolved_name or default_display_name(resolved_id),
                resolved_language,
                resolved_instruct,
            )
            console.print(table)
            return
        record = create_designed_voice(
            voice_id=resolved_id,
            name=resolved_name,
            instruct=resolved_instruct,
            text=resolved_text,
            language=resolved_language,
            library=lib,
            overwrite=overwrite,
        )
        if context.json_output:
            emit_json(
                {
                    "voice": model_object(record),
                    "paths": {
                        "voice": str(lib / record.id),
                        "reference_audio": str(lib / record.id / "reference.wav"),
                        "metadata": str(lib / record.id / "voice.json"),
                    },
                }
            )
            return
        console.print(f"[green]Created voice:[/] {record.id} → {lib / record.id}")

    run_cli_action(context, run)


@create_app.command("design-batch")
def design_batch(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="JSONL or TXT prompt file.")],
    text: Annotated[str | None, typer.Option("--text", help="Global seed text.")] = None,
    language: Annotated[
        str,
        typer.Option("--language", help="Language for VoiceDesign generation."),
    ] = DEFAULT_LANGUAGE,
    library: LibraryOption = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing voices.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without generating.")] = False,
) -> None:
    """Generate multiple voices from a prompt file."""
    context = context_from_typer(ctx)

    def run() -> None:
        lib = get_library_path(library)
        resolved_language = require_supported_language(language)
        prompts = load_prompts(file, default_text=text, default_language=resolved_language)
        if dry_run:
            items: list[dict[str, object]] = [
                {
                    "id": prompt.id,
                    "name": prompt.name or default_display_name(prompt.id),
                    "language": prompt.language or resolved_language,
                    "instruct": prompt.instruct,
                    "text": prompt.text or text,
                }
                for prompt in prompts
            ]
            if context.json_output:
                emit_json(collection_payload(items, len(items)))
                return
            table = Table(title="Dry Run — voices to create")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Language")
            table.add_column("Instruct", max_width=50)
            for prompt in prompts:
                table.add_row(
                    prompt.id,
                    prompt.name or default_display_name(prompt.id),
                    prompt.language or resolved_language,
                    prompt.instruct,
                )
            console.print(table)
            return
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=err_console if context.json_output else console,
        ) as progress:
            progress.add_task("Generating voices…", total=len(prompts))
            successes, failures = create_voice_batch(
                prompts=prompts,
                default_text=text,
                default_language=resolved_language,
                library=lib,
                overwrite=overwrite,
            )
        if context.json_output:
            success_items: list[dict[str, object]] = [
                {
                    "status": "ok",
                    "voice": model_object(record),
                    "paths": {
                        "voice": str(lib / record.id),
                        "reference_audio": str(lib / record.id / "reference.wav"),
                        "metadata": str(lib / record.id / "voice.json"),
                    },
                }
                for record in successes
            ]
            failure_items: list[dict[str, object]] = [
                {
                    "status": "error",
                    "id": voice_id,
                    "message": message,
                }
                for voice_id, message in failures
            ]
            emit_json(collection_payload([*success_items, *failure_items], len(prompts)))
            if failures:
                raise SystemExit(4)
            return
        table = Table(title="Batch Results")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Status")
        for record in successes:
            table.add_row(record.id, record.name, "[green]OK[/]")
        for voice_id, message in failures:
            table.add_row(voice_id, "", f"[red]{message}[/]")
        console.print(table)
        if failures:
            raise SystemExit(4)

    run_cli_action(context, run)
