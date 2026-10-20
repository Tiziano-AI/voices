"""Root CLI commands for playback and rendered speech artifacts."""

import tempfile
from pathlib import Path
from typing import Annotated

import typer

from voices.cli_json import context_from_typer, emit_json, model_object, run_cli_action
from voices.cli_support import LibraryOption, console, play_wav, resolve_render_text, select_voice_id
from voices.config import DEFAULT_OUTPUT_DIR, get_library_path
from voices.domain.errors import InvalidInputError
from voices.store.library_store import write_wav
from voices.store.output_store import output_artifact_for_name
from voices.workflow.synthesize_voice import render_speech, synthesize_to_memory


def register_speech_commands(root: typer.Typer) -> None:
    """Register root commands that speak text or render persisted speech."""

    @root.command()
    def say(
        ctx: typer.Context,
        text: Annotated[str, typer.Argument(help="Text to speak aloud.")],
        voice: Annotated[str | None, typer.Option("--voice", help="Voice ID. Default: most recent.")] = None,
        language: Annotated[str | None, typer.Option("--language", help="Override voice language.")] = None,
        library: LibraryOption = None,
    ) -> None:
        """Speak text aloud through your Mac speakers."""
        context = context_from_typer(ctx)

        def run() -> None:
            spoken_text = text.strip()
            if not spoken_text:
                raise InvalidInputError("Text must not be empty.")
            lib = get_library_path(library)
            voice_id = select_voice_id(lib, voice)
            with tempfile.TemporaryDirectory() as temp_dir_name:
                audio_data, sample_rate, _record = synthesize_to_memory(
                    voice_id=voice_id,
                    text=spoken_text,
                    language=language,
                    library=lib,
                )
                wav_path = Path(temp_dir_name) / "say.wav"
                write_wav(wav_path, audio_data, sample_rate)
                if context.json_output:
                    play_wav(wav_path)
                    emit_json({"voice_id": voice_id, "text": spoken_text, "played": True})
                else:
                    console.print(f"[dim]{voice_id}:[/] {spoken_text}")
                    play_wav(wav_path)

        run_cli_action(context, run)

    @root.command()
    def render(
        ctx: typer.Context,
        voice_id: Annotated[str, typer.Argument(help="Voice identifier.")],
        text: Annotated[str | None, typer.Argument(help="Text to synthesize.")] = None,
        text_file: Annotated[Path | None, typer.Option("--text-file", help="Read text from file instead.")] = None,
        language: Annotated[str | None, typer.Option("--language", help="Override voice language.")] = None,
        out_dir: Annotated[Path, typer.Option("--out-dir", help="Output directory.")] = DEFAULT_OUTPUT_DIR,
        model_revision: Annotated[
            str | None,
            typer.Option("--model-revision", help="Exact Base model commit SHA (40 hexadecimal characters)."),
        ] = None,
        play: Annotated[bool, typer.Option("--play", help="Play audio through speakers after saving.")] = False,
        library: LibraryOption = None,
    ) -> None:
        """Render text to a WAV file using a saved voice."""
        context = context_from_typer(ctx)

        def run() -> None:
            resolved_text = resolve_render_text(text, text_file)
            wav_path = render_speech(
                voice_id=voice_id,
                text=resolved_text,
                language=language,
                library=get_library_path(library),
                out_dir=out_dir,
                model_revision=model_revision,
            )
            if context.json_output:
                artifact = output_artifact_for_name(out_dir, voice_id, wav_path.name)
                if play:
                    play_wav(wav_path)
                emit_json(
                    {
                        "artifact": model_object(artifact.record),
                        "paths": {
                            "wav": str(artifact.wav_path),
                            "sidecar": str(artifact.sidecar_path),
                        },
                    }
                )
                return
            console.print(f"[green]Output:[/] {wav_path}")
            if play:
                play_wav(wav_path)

        run_cli_action(context, run)
