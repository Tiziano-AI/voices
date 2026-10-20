"""Interactive clone and record transcript review helpers."""

from pathlib import Path

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from voices import config
from voices.adapter.ffmpeg_audio import free_recording, record_guided_audio
from voices.cli_support import console, err_console, play_wav
from voices.domain.create_contracts import CloneReviewRequest, TranscriptionDraft, get_guided_recording_script
from voices.domain.errors import InvalidInputError, VoicesError
from voices.workflow.clone_voice import prepare_clone_review


def prompt_non_empty(label: str, default: str) -> str:
    """Prompt until the operator provides one non-empty value."""
    while True:
        value = Prompt.ask(label, default=default).strip()
        if value:
            return value
        err_console.print(f"[bold red]Error:[/] {label} must not be empty.")


def _play_review_take(audio_path: Path) -> None:
    """Play one recorded or imported take without aborting the review loop on failure."""
    try:
        play_wav(audio_path)
    except VoicesError as error:
        err_console.print(f"[bold red]Playback failed:[/] {error}")


def _render_transcript_panel(draft: TranscriptionDraft) -> Panel:
    """Render one transcript draft with the highest-signal review context."""
    segment_table = Table(show_header=True, box=None, pad_edge=False)
    segment_table.add_column("Start", no_wrap=True, style="bold")
    segment_table.add_column("End", no_wrap=True)
    segment_table.add_column("Text")
    for segment in draft.segments:
        segment_table.add_row(f"{segment.start:.1f}s", f"{segment.end:.1f}s", segment.text)
    title = f"Transcript · {draft.language} · {draft.duration_seconds:.1f}s"
    content = Table(show_header=False, box=None, pad_edge=False)
    content.add_column("Key", style="bold")
    content.add_column("Value")
    content.add_row("draft", draft.transcript)
    content.add_row("segments", "")
    content.add_row("", segment_table)
    return Panel(content, title=title)


def _review_transcription_failure(
    error: VoicesError,
    *,
    retry_reruns_stt_only: bool,
    playback_path: Path,
) -> str | None:
    """Handle one review-stage transcription failure and return an approved transcript or retry."""
    err_console.print(f"[bold red]Review failed:[/] {error}")
    while True:
        action = Prompt.ask("Transcript", choices=["retry", "edit", "play"], default="edit")
        if action == "retry":
            if retry_reruns_stt_only:
                console.print("[dim]Retrying transcription on the same audio.[/]")
            else:
                console.print("[dim]Retrying with a fresh recording.[/]")
            return None
        if action == "play":
            _play_review_take(playback_path)
            continue
        return prompt_non_empty("Approved transcript", "")


def _review_transcript_draft(
    draft: TranscriptionDraft,
    *,
    retry_reruns_stt_only: bool,
    playback_path: Path,
) -> str | None:
    """Return the approved transcript or `None` when the operator wants a retry."""
    console.print(_render_transcript_panel(draft))
    while True:
        action = Prompt.ask("Transcript", choices=["accept", "retry", "edit", "play"], default="accept")
        if action == "accept":
            return draft.transcript
        if action == "retry":
            if retry_reruns_stt_only:
                console.print("[dim]Retrying transcription on the same audio.[/]")
            else:
                console.print("[dim]Discarding the take and recording again.[/]")
            return None
        if action == "play":
            _play_review_take(playback_path)
            continue
        return prompt_non_empty("Approved transcript", draft.transcript)


def _capture_guided_take(audio_path: Path, language: str, script: str) -> None:
    """Capture one timed guided take."""
    console.print(
        Panel(
            script,
            title=f"Read aloud · {language}",
            subtitle=f"Auto-stops after {config.GUIDED_RECORD_TARGET_SECONDS:.0f}s",
        )
    )
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Recording guided take…", total=None)
        record_guided_audio(audio_path, config.GUIDED_RECORD_TARGET_SECONDS, sample_rate=config.FALLBACK_SAMPLE_RATE)


def _capture_free_take(audio_path: Path) -> None:
    """Capture one free take until the operator stops it."""
    console.print("[cyan]Recording now.[/] Press [bold]Enter[/] to stop.")
    try:
        with free_recording(audio_path, sample_rate=config.FALLBACK_SAMPLE_RATE):
            console.input()
    except BaseException as error:
        for note in getattr(error, "__notes__", ()):
            err_console.print(note, markup=False)
        if isinstance(error, (EOFError, KeyboardInterrupt)):
            raise typer.Abort() from error
        raise


def _capture_recording(
    *,
    audio_path: Path,
    mode: str,
    language: str,
    script: str | None,
) -> None:
    """Capture one guided or free recording into the provided path."""
    if mode == "guided":
        guided_script = script or get_guided_recording_script(language)
        _capture_guided_take(audio_path, language, guided_script)
        return
    _capture_free_take(audio_path)


def record_and_review(
    audio_path: Path,
    mode: str,
    language: str,
    script: str | None,
    library: Path,
) -> str:
    """Record one or more takes until the operator approves a transcript."""
    review_policy = "record_guided" if mode == "guided" else "record_free"
    review_request = CloneReviewRequest(
        language=language,
        review_policy=review_policy,
        fallback_name="Voice",
    )
    while True:
        _capture_recording(audio_path=audio_path, mode=mode, language=language, script=script)
        try:
            prepared = prepare_clone_review(audio_path=audio_path, library=library, request=review_request)
        except InvalidInputError as error:
            err_console.print(f"[bold red]Error:[/] {error}")
            console.print("[dim]Recording again.[/]")
            continue
        except VoicesError as error:
            approved_transcript = _review_transcription_failure(
                error,
                retry_reruns_stt_only=False,
                playback_path=audio_path,
            )
            if approved_transcript is not None:
                return approved_transcript
            continue
        approved_transcript = _review_transcript_draft(
            prepared.draft,
            retry_reruns_stt_only=False,
            playback_path=audio_path,
        )
        if approved_transcript is not None:
            return approved_transcript
