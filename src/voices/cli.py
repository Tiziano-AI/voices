"""Root Typer application for the local-first voices product."""

from typing import Annotated

import typer

from voices.cli_align import register_alignment_commands
from voices.cli_clone import clone_app
from voices.cli_create import create_app
from voices.cli_diagnostics import register_diagnostic_commands
from voices.cli_edge import edge_app
from voices.cli_json import CliContext
from voices.cli_library import register_library_commands
from voices.cli_outputs import outputs_app
from voices.cli_record import record_app
from voices.cli_speech import register_speech_commands
from voices.cli_transcribe import register_transcription_commands

app = typer.Typer(name="voices", help="Local MLX voice library CLI using Qwen3-TTS.")
app.add_typer(create_app)
app.add_typer(clone_app, name="clone")
app.add_typer(record_app, name="record")
app.add_typer(outputs_app, name="outputs")
app.add_typer(edge_app, name="edge")


@app.callback()
def configure(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON to stdout.")] = False,
) -> None:
    """Configure global CLI output behavior before command handlers run."""
    ctx.obj = CliContext(json_output=json_output)


register_diagnostic_commands(app)
register_library_commands(app)
register_speech_commands(app)
register_alignment_commands(app)
register_transcription_commands(app)
