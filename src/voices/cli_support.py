"""Shared CLI helpers and operator-facing rendering for the voices product."""

import subprocess
from pathlib import Path
from typing import Annotated, Never

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from voices.domain.contracts import VoiceRecord, require_non_empty_text
from voices.domain.errors import InvalidInputError, PlaybackError, VoiceNotFoundError, VoicesError
from voices.store.library_store import list_voice_records

console = Console()
err_console = Console(stderr=True)
EMPTY_LIBRARY_GUIDANCE = (
    "No voices found. Create one first with 'voices design', "
    "'voices clone review' plus 'voices clone save', or 'voices record'."
)

LibraryOption = Annotated[
    Path | None,
    typer.Option("--library", help="Voice library directory."),
]
LanguageOption = Annotated[
    str,
    typer.Option("--language", help="Language for synthesis."),
]


def exit_for_error(error: VoicesError) -> Never:
    """Render one domain error and terminate with its declared exit code."""
    err_console.print(f"[bold red]Error:[/] {error}")
    raise SystemExit(error.exit_code) from error


def default_display_name(voice_id: str) -> str:
    """Build the default display label shown to operators."""
    return voice_id.replace("_", " ").replace("-", " ").title()


def resolve_optional_name(requested_name: str | None) -> str | None:
    """Validate one optional CLI display name."""
    if requested_name is None:
        return None
    return require_non_empty_text("voice name", requested_name)


def play_wav(path: Path) -> None:
    """Play one WAV file through macOS afplay."""
    try:
        subprocess.run(["afplay", str(path)], check=True)
    except FileNotFoundError as error:
        raise PlaybackError("afplay is not available on this Mac.") from error
    except subprocess.CalledProcessError as error:
        raise PlaybackError(f"afplay failed with exit code {error.returncode}.") from error


def resolve_render_text(text: str | None, text_file: Path | None) -> str:
    """Validate the render text inputs and return the final text payload."""
    if text and text_file:
        raise InvalidInputError("Provide text or --text-file, not both.")
    if text_file is not None:
        try:
            file_text = text_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise InvalidInputError(f"Unable to read text file '{text_file}': {error}") from error
        if not file_text:
            raise InvalidInputError("The --text-file content must not be empty.")
        return file_text
    if text is None or not text.strip():
        raise InvalidInputError("Provide text or --text-file.")
    return text.strip()


def select_voice_id(library: Path, requested_voice_id: str | None) -> str:
    """Resolve the requested voice or fall back to the most recently created voice."""
    if requested_voice_id:
        return requested_voice_id
    records = list_voice_records(library)
    if not records:
        raise VoiceNotFoundError(EMPTY_LIBRARY_GUIDANCE)
    return records[-1].id


def render_voice_table(records: list[VoiceRecord]) -> Table:
    """Build the canonical list table for saved voices."""
    table = Table(title="Voices", expand=True)
    table.add_column("id", no_wrap=True)
    table.add_column("lang", no_wrap=True)
    table.add_column("source", no_wrap=True)
    table.add_column("desc", overflow="fold", ratio=1)
    for record in records:
        table.add_row(
            record.id,
            record.language,
            record.source_kind(),
            record.description(),
        )
    return table


def render_record_panel(record: VoiceRecord) -> Panel:
    """Build the canonical detail panel for one saved voice."""
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    payload = record.model_dump(mode="json")
    for key, value in payload.items():
        table.add_row(key, str(value))
    table.add_row("description", record.description())
    table.add_row("source_kind", record.source_kind())
    return Panel(table, title=f"Voice: {record.id}")
