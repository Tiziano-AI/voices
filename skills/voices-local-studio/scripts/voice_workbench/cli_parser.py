"""Parser construction for the voices prompt workbench."""

from __future__ import annotations

import argparse
from pathlib import Path

from .cli_audit_handler import handle_audit
from .cli_handlers import handle_compose, handle_scaffold


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Structured authoring workbench for the local voices product.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_scaffold_parser(subparsers)
    _add_compose_parser(subparsers)
    _add_audit_parser(subparsers)
    return parser


def _add_scaffold_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    scaffold_parser = subparsers.add_parser("scaffold", help="Emit starter structured specs.")
    scaffold_group = scaffold_parser.add_mutually_exclusive_group()
    scaffold_group.add_argument("--single", action="store_true", help="Emit one starter spec object.")
    scaffold_group.add_argument("--pack", type=int, metavar="N", help="Emit an array of N starter specs.")
    scaffold_parser.set_defaults(handler=handle_scaffold)


def _add_compose_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    compose_parser = subparsers.add_parser("compose", help="Compile structured specs into JSONL prompt rows.")
    compose_parser.add_argument("input_path", type=Path, help="Path to a JSON object, or array spec.")
    compose_parser.add_argument(
        "--profile",
        choices=("plain", "balanced", "balanced-literary"),
        default="balanced-literary",
        help="Prompt prose profile.",
    )
    compose_parser.set_defaults(handler=handle_compose)


def _add_audit_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    audit_parser = subparsers.add_parser("audit", help="Audit prompts, packs, or structured specs.")
    audit_parser.add_argument("source", type=Path, nargs="?", help="JSON, JSONL, or TXT file to audit.")
    audit_parser.add_argument("--instruct", help="Single prose prompt to audit.")
    audit_parser.add_argument("--default-text", help="Shared seed text for TXT prompt packs.")
    audit_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    audit_parser.add_argument("--strict-imitation", action="store_true", help="Escalate imitation findings.")
    audit_parser.set_defaults(handler=handle_audit)
