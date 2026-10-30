"""Root Typer application for the local-first voices product."""

from pathlib import Path
from typing import Annotated, Literal

import typer

from voices.cli_align import register_alignment_commands
from voices.cli_clone import clone_app
from voices.cli_compute import compute_app
from voices.cli_create import create_app
from voices.cli_diagnostics import register_diagnostic_commands
from voices.cli_edge import edge_app
from voices.cli_json import CliContext, run_cli_action
from voices.cli_library import register_library_commands
from voices.cli_outputs import outputs_app
from voices.cli_record import record_app
from voices.cli_speech import register_speech_commands
from voices.cli_transcribe import register_transcription_commands
from voices.compute import ComputeSelection

app = typer.Typer(name="voices", help="Local voice studio; MLX default, optional explicit DGX compute.")
app.add_typer(create_app)
app.add_typer(clone_app, name="clone")
app.add_typer(record_app, name="record")
app.add_typer(outputs_app, name="outputs")
app.add_typer(edge_app, name="edge")
app.add_typer(compute_app, name="compute")


@app.callback()
def configure(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON to stdout.")] = False,
    compute: Annotated[
        Literal["mlx", "dgx"], typer.Option("--compute", help="Compute for this invocation/session; no fallback.")
    ] = "mlx",
    dgx_host: Annotated[str | None, typer.Option("--dgx-host", help="Existing authenticated SSH host alias.")] = None,
    dgx_ssh_config: Annotated[
        Path | None, typer.Option("--dgx-ssh-config", help="Existing SSH configuration file.")
    ] = None,
    compute_state: Annotated[
        Path, typer.Option("--compute-state", help="Private invocation/recovery custody, not the voice library.")
    ] = Path("~/.local/state/voices/compute"),
) -> None:
    """Configure global CLI output behavior before command handlers run."""

    def select() -> None:
        ctx.obj = CliContext(
            json_output=json_output, compute=ComputeSelection(compute, dgx_host, dgx_ssh_config, compute_state)
        )

    run_cli_action(CliContext(json_output=json_output), select)


register_diagnostic_commands(app)
register_library_commands(app)
register_speech_commands(app)
register_alignment_commands(app)
register_transcription_commands(app)
