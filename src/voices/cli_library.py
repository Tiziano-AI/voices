"""Root CLI commands for inspecting and managing saved voices."""

from pathlib import Path
from typing import Annotated

import typer

from voices.cli_json import (
    collection_payload,
    context_from_typer,
    emit_json,
    model_object,
    require_limit,
    run_cli_action,
)
from voices.cli_support import EMPTY_LIBRARY_GUIDANCE, LibraryOption, console, render_record_panel, render_voice_table
from voices.config import get_library_path
from voices.domain.contracts import VoiceRecord, require_optional_supported_language
from voices.domain.errors import InvalidInputError, VoiceNotFoundError
from voices.store.library_store import delete_voice_record, list_voice_records, load_voice_record


def register_library_commands(root: typer.Typer) -> None:
    """Register root commands that read, resolve, show, and delete saved voices."""

    @root.command("list")
    def list_voices(
        ctx: typer.Context,
        language: Annotated[str | None, typer.Option("--language", help="Filter by language.")] = None,
        source: Annotated[str | None, typer.Option("--source", help="Filter by source kind: design or clone.")] = None,
        query: Annotated[str | None, typer.Option("--query", help="Filter by id, name, or description text.")] = None,
        limit: Annotated[int | None, typer.Option("--limit", help="Maximum voices to return.")] = None,
        library: LibraryOption = None,
    ) -> None:
        """List all saved voices."""
        context = context_from_typer(ctx)

        def run() -> None:
            resolved_limit = require_limit(limit)
            records = _filter_records(
                list_voice_records(get_library_path(library)),
                language=language,
                source=source,
                query=query,
            )
            limited_records = records[:resolved_limit] if resolved_limit is not None else records
            if context.json_output:
                emit_json(collection_payload([_voice_summary(record) for record in limited_records], resolved_limit))
                return
            if not limited_records:
                console.print(f"[dim]{EMPTY_LIBRARY_GUIDANCE}[/]")
                return
            console.print(render_voice_table(limited_records))

        run_cli_action(context, run)

    @root.command()
    def resolve(
        ctx: typer.Context,
        query: Annotated[str, typer.Argument(help="Voice id, display name, or unambiguous search text.")],
        library: LibraryOption = None,
    ) -> None:
        """Resolve human input into one stable voice id."""
        context = context_from_typer(ctx)

        def run() -> None:
            lib = get_library_path(library)
            record, match = _resolve_voice_record(lib, query)
            payload: dict[str, object] = {
                "voice_id": record.id,
                "match": match,
                "voice": _voice_summary(record),
                "paths": _voice_paths(lib, record.id),
            }
            if context.json_output:
                emit_json(payload)
                return
            console.print(record.id)

        run_cli_action(context, run)

    @root.command()
    def show(
        ctx: typer.Context,
        voice_id: Annotated[str, typer.Argument(help="Voice identifier.")],
        library: LibraryOption = None,
    ) -> None:
        """Show full metadata for a voice."""
        context = context_from_typer(ctx)

        def run() -> None:
            lib = get_library_path(library)
            record = load_voice_record(lib, voice_id)
            if context.json_output:
                emit_json(_voice_payload(lib, record))
                return
            console.print(render_record_panel(record))

        run_cli_action(context, run)

    @root.command()
    def delete(
        ctx: typer.Context,
        voice_id: Annotated[str, typer.Argument(help="Voice identifier.")],
        yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation.")] = False,
        dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview deletion without removing files.")] = False,
        library: LibraryOption = None,
    ) -> None:
        """Delete a saved voice."""
        context = context_from_typer(ctx)
        if not yes and not dry_run and not context.json_output:
            typer.confirm(f"Delete voice '{voice_id}'?", abort=True)

        def run() -> None:
            lib = get_library_path(library)
            record = load_voice_record(lib, voice_id)
            payload: dict[str, object] = {
                "voice": model_object(record),
                "paths": _voice_paths(lib, record.id),
                "dry_run": dry_run,
                "deleted": not dry_run,
            }
            if context.json_output and not yes and not dry_run:
                raise InvalidInputError("JSON delete requires --dry-run or --yes.")
            if dry_run:
                if context.json_output:
                    emit_json(payload)
                    return
                console.print(f"[yellow]Would delete:[/] {voice_id}")
                return
            delete_voice_record(lib, voice_id)
            if context.json_output:
                emit_json(payload)
                return
            console.print(f"[green]Deleted:[/] {voice_id}")

        run_cli_action(context, run)


def _voice_paths(library: Path, voice_id: str) -> dict[str, object]:
    """Return resolved persisted paths for one saved voice."""
    voice_path = library / voice_id
    return {
        "voice": str(voice_path),
        "reference_audio": str(voice_path / "reference.wav"),
        "reference_text": str(voice_path / "reference.txt"),
        "metadata": str(voice_path / "voice.json"),
    }


def _voice_summary(record: VoiceRecord) -> dict[str, object]:
    """Project one saved voice into a CLI summary object."""
    return {
        "id": record.id,
        "name": record.name,
        "language": record.language,
        "source_kind": record.source_kind(),
        "description": record.description(),
        "created_at": record.created_at,
    }


def _voice_payload(library: Path, record: VoiceRecord) -> dict[str, object]:
    """Project one saved voice into the exact-read JSON shape."""
    return {
        "voice": model_object(record),
        "summary": _voice_summary(record),
        "paths": _voice_paths(library, record.id),
    }


def _filter_records(
    records: list[VoiceRecord],
    *,
    language: str | None,
    source: str | None,
    query: str | None,
) -> list[VoiceRecord]:
    """Apply CLI list filters to saved voices."""
    resolved_language = require_optional_supported_language(language)
    resolved_source = None if source is None else source.strip().lower()
    if resolved_source is not None and resolved_source not in {"design", "clone"}:
        raise InvalidInputError("--source must be 'design' or 'clone'.")
    resolved_query = None if query is None else query.strip().lower()
    filtered: list[VoiceRecord] = []
    for record in records:
        if resolved_language is not None and record.language != resolved_language:
            continue
        if resolved_source is not None and record.source_kind() != resolved_source:
            continue
        if resolved_query:
            haystack = " ".join((record.id, record.name, record.language, record.source_kind(), record.description()))
            if resolved_query not in haystack.lower():
                continue
        filtered.append(record)
    return filtered


def _resolve_voice_record(library: Path, query: str) -> tuple[VoiceRecord, str]:
    """Resolve human input into one saved voice record and match reason."""
    records = list_voice_records(library)
    normalized = query.strip()
    if not normalized:
        raise InvalidInputError("resolve query must not be empty.")
    for record in records:
        if record.id == normalized:
            return record, "id"
    lowered = normalized.lower()
    exact_name_matches = [record for record in records if record.name.lower() == lowered]
    if len(exact_name_matches) == 1:
        return exact_name_matches[0], "name"
    fuzzy_matches = [
        record
        for record in records
        if lowered in record.id.lower() or lowered in record.name.lower() or lowered in record.description().lower()
    ]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0], "fuzzy"
    if not fuzzy_matches and not exact_name_matches:
        raise VoiceNotFoundError(f"No voice resolved from '{query}'.")
    candidates = ", ".join(record.id for record in [*exact_name_matches, *fuzzy_matches])
    raise InvalidInputError(f"Resolve query '{query}' is ambiguous. Candidates: {candidates}")
