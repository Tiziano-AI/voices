"""Root CLI commands for diagnostics, language discovery, and studio launch."""

import os
import shutil
from pathlib import Path
from typing import Annotated

import typer
from huggingface_hub.constants import HF_HUB_CACHE
from rich.table import Table

from voices import config
from voices.cli_json import collection_payload, context_from_typer, emit_json, run_cli_action
from voices.cli_support import LibraryOption, console
from voices.config import DEFAULT_OUTPUT_DIR, get_library_path
from voices.domain.contracts import SUPPORTED_LANGUAGE_LABELS
from voices.domain.errors import InvalidInputError
from voices.edge.app import LaunchOptions, launch_edge_server, loopback_url, require_loopback_host
from voices.runtime_identity import get_runtime_identity
from voices.store.library_store import list_voice_records
from voices.studio_bundle import studio_bundle_path


def register_diagnostic_commands(root: typer.Typer) -> None:
    """Register root commands that inspect readiness, languages, and the bundled studio."""

    @root.command("ui")
    def ui(
        ctx: typer.Context,
        host: Annotated[str, typer.Option("--host", help="Local host for the bundled studio.")] = "127.0.0.1",
        port: Annotated[int, typer.Option("--port", help="Local port for the bundled studio.")] = 8765,
        no_open: Annotated[bool, typer.Option("--no-open", help="Do not open the browser automatically.")] = False,
        library: LibraryOption = None,
    ) -> None:
        """Launch the bundled local browser studio."""
        context = context_from_typer(ctx)

        def run() -> None:
            if context.json_output:
                raise InvalidInputError("JSON mode does not launch the browser studio.")
            lib = get_library_path(library)
            resolved_host = require_loopback_host(host)
            console.print(f"[cyan]Studio:[/] {loopback_url(resolved_host, port)}")
            launch_edge_server(
                library=lib,
                out_dir=DEFAULT_OUTPUT_DIR,
                launch=LaunchOptions(host=resolved_host, port=port, open_browser=not no_open),
                compute=context.compute,
            )

        run_cli_action(context, run)

    @root.command()
    def doctor(ctx: typer.Context, library: LibraryOption = None) -> None:
        """Inspect local product readiness without loading models."""
        context = context_from_typer(ctx)

        def run() -> None:
            if context.json_output:
                payload = _doctor_payload(library)
                payload["compute"] = context.compute.describe()
                emit_json(payload)
                return

            lib = get_library_path(library)
            records = list_voice_records(lib)
            ffmpeg_path = shutil.which("ffmpeg")
            table = Table(title="Voices Doctor", show_header=False)
            table.add_column("Check", style="bold", no_wrap=True)
            table.add_column("Value", overflow="fold")
            table.add_row("library", _readiness_value(lib))
            table.add_row("voices", str(len(records)))
            table.add_row("outputs", _readiness_value(DEFAULT_OUTPUT_DIR))
            web_dist = studio_bundle_path()
            table.add_row("studio bundle", _readiness_value(web_dist, required_file=web_dist / "index.html"))
            ffmpeg_value = ffmpeg_path if ffmpeg_path is not None else "missing; clone and record need ffmpeg"
            table.add_row("ffmpeg", str(ffmpeg_value))
            runtime = get_runtime_identity()
            table.add_row("python", f"{runtime.python} ({runtime.executable})")
            table.add_row("source", runtime.source_sha256)
            table.add_row(
                "compute",
                context.compute.backend + (f" ({context.compute.ssh_host})" if context.compute.ssh_host else ""),
            )
            table.add_row("model cache", str(Path(HF_HUB_CACHE).expanduser().resolve()))
            console.print(table)

        run_cli_action(context, run)

    @root.command()
    def languages(ctx: typer.Context) -> None:
        """List supported language labels."""
        context = context_from_typer(ctx)

        def run() -> None:
            items: list[dict[str, object]] = [{"language": language} for language in SUPPORTED_LANGUAGE_LABELS]
            if context.json_output:
                emit_json(collection_payload(items, None))
                return
            table = Table(title="Languages")
            table.add_column("language")
            for language in SUPPORTED_LANGUAGE_LABELS:
                table.add_row(language)
            console.print(table)

        run_cli_action(context, run)


def _readiness_value(path: Path, required_file: Path | None = None) -> str:
    """Render one path with a simple existence state."""
    resolved = path.expanduser().resolve(strict=False)
    if required_file is None:
        ready = resolved.exists()
    else:
        ready = required_file.expanduser().resolve(strict=False).is_file()
    state = "ready" if ready else "missing"
    return f"{resolved} ({state})"


def _library_source(cli_override: Path | None) -> dict[str, object]:
    """Return the active library source and documented precedence."""
    env_value = os.environ.get("VOICES_LIBRARY")
    if cli_override is not None:
        source = "cli"
        detail = "--library"
    elif env_value:
        source = "env"
        detail = "VOICES_LIBRARY"
    else:
        source = "default"
        detail = "~/.voices"
    return {
        "source": source,
        "detail": detail,
        "precedence": ["--library", "VOICES_LIBRARY", "~/.voices"],
    }


def _doctor_payload(library: Path | None) -> dict[str, object]:
    """Build the readiness payload without loading MLX models."""
    lib = get_library_path(library)
    records = list_voice_records(lib)
    output_root = DEFAULT_OUTPUT_DIR.expanduser().resolve(strict=False)
    web_dist = studio_bundle_path()
    web_index = web_dist / "index.html"
    ffmpeg_path = shutil.which("ffmpeg")
    return {
        "auth_required": False,
        "library": {
            **_library_source(library),
            "path": str(lib),
            "exists": lib.exists(),
            "voice_count": len(records),
        },
        "outputs": {
            "path": str(output_root),
            "exists": output_root.exists(),
        },
        "studio_bundle": {
            "path": str(web_dist),
            "index_html": str(web_index),
            "ready": web_index.is_file(),
        },
        "ffmpeg": {
            "ready": ffmpeg_path is not None,
            "path": ffmpeg_path,
        },
        "runtime": get_runtime_identity().model_dump(mode="json"),
        "model_cache": str(Path(HF_HUB_CACHE).expanduser().resolve()),
        "models": {
            "base": config.BASE_MODEL,
            "voice_design": config.VOICE_DESIGN_MODEL,
            "stt": config.STT_MODEL,
            "aligner": config.ALIGNER_MODEL,
        },
        "model_revisions": {
            "base": config.BASE_MODEL_REVISION,
            "voice_design": config.VOICE_DESIGN_MODEL_REVISION,
            "stt": config.STT_MODEL_REVISION,
            "aligner": config.ALIGNER_MODEL_REVISION,
        },
    }
