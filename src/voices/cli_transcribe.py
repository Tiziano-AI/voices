"""Canonical CLI ingress for recognition from an existing WAV."""

from pathlib import Path
from typing import Annotated

import typer

from voices.cli_json import context_from_typer, emit_json, model_object, run_cli_action
from voices.cli_support import console
from voices.workflow.transcribe_speech import transcribe_speech


def register_transcription_commands(root: typer.Typer) -> None:
    @root.command()
    def transcribe(
        ctx: typer.Context,
        audio: Annotated[Path, typer.Option("--audio", help="Existing WAV file; never modified.")],
        language: Annotated[
            str, typer.Option("--language", help="Public Voices language label, for example English or Italian.")
        ],
        model_revision: Annotated[
            str, typer.Option("--model-revision", help="Required exact ASR model commit SHA (40 hex characters).")
        ],
    ) -> None:
        """Recognize words from a WAV; no capture, playback or voice/library writes.

        Runs local ASR and may download its pinned snapshot to the shared model cache.
        Global --json returns transcript, input audio hashes, model and runtime identity.
        No supplied transcript is accepted; recognition is not a quality verdict.
        """
        context = context_from_typer(ctx)

        def run() -> None:
            result = transcribe_speech(audio=audio, language=language, model_revision=model_revision)
            if context.json_output:
                emit_json(model_object(result))
                return
            console.print(result.transcript, markup=False, highlight=False)

        run_cli_action(context, run)
