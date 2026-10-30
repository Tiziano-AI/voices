"""Recovery of an existing compute occurrence, never an inference replay."""

import typer

from voices.adapter.dgx_compute import inspect_invocation, recover_invocation
from voices.cli_json import context_from_typer, emit_json, run_cli_action
from voices.domain.errors import InvalidInputError

compute_app = typer.Typer(help="Inspect or collect one retained DGX invocation; never resubmit it.")


@compute_app.command("inspect")
def inspect(ctx: typer.Context, invocation: str) -> None:
    context = context_from_typer(ctx)

    def run() -> None:
        if context.compute.backend != "dgx":
            raise InvalidInputError("Recovery requires the original --compute dgx SSH selection.")
        emit_json(inspect_invocation(context.compute, invocation))

    run_cli_action(context, run)


@compute_app.command("collect")
def collect(ctx: typer.Context, invocation: str) -> None:
    context = context_from_typer(ctx)

    def run() -> None:
        result = recover_invocation(context.compute, invocation)
        emit_json(
            {
                "invocation": invocation,
                "runtime": result.runtime.model_dump(mode="json"),
                "custody": str(context.compute.state_root.expanduser().resolve() / invocation),
                "library_published": False,
                "regenerated": False,
            }
        )

    run_cli_action(context, run)
