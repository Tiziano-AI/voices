"""Canonical CLI ingress for supplied-text word timing."""

from pathlib import Path
from typing import Annotated

import typer

from voices.cli_json import context_from_typer, emit_json, model_object, run_cli_action
from voices.cli_support import console
from voices.workflow.align_speech import align_speech


def register_alignment_commands(root: typer.Typer) -> None:
    @root.command()
    def align(
        ctx: typer.Context,
        audio: Annotated[Path, typer.Option("--audio", help="Existing audio file; never modified.")],
        text_file: Annotated[Path, typer.Option("--text-file", help="UTF-8 supplied transcript file.")],
        language: Annotated[str, typer.Option("--language", help="Supported Voices language label.")],
        model_revision: Annotated[
            str | None, typer.Option("--model-revision", help="Exact aligner model commit SHA (40 hex characters).")
        ] = None,
    ) -> None:
        """Estimate supplied-word times; this does not verify spoken content."""
        context = context_from_typer(ctx)

        def run() -> None:
            result = align_speech(
                audio=audio,
                text_file=text_file,
                language=language,
                model_revision=model_revision,
                compute=context.compute,
            )
            if context.json_output:
                emit_json(model_object(result))
                return
            console.print("[yellow]Estimated supplied-word timing; spoken content is not verified.[/]")
            for word in result.words:
                console.print(f"{word.start:.3f}\t{word.end:.3f}\t{word.text}", markup=False)

        run_cli_action(context, run)
