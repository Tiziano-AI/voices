"""CLI command handlers for the voices prompt workbench."""

from __future__ import annotations

import argparse
import json
import sys

from .compose import compose_instruct, load_json_path, parse_spec_input, starter_spec
from .contracts import WorkbenchError


def handle_scaffold(args: argparse.Namespace) -> int:
    """Emit starter structured specs."""
    if args.pack is not None and args.pack <= 0:
        raise WorkbenchError("--pack must be greater than 0.")
    payload = [starter_spec(index) for index in range(1, args.pack + 1)] if args.pack is not None else starter_spec(1)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("Hint: fill purpose, cadence, and two timbre traits before composing.", file=sys.stderr)
    return 0


def handle_compose(args: argparse.Namespace) -> int:
    """Compile structured specs into canonical JSONL rows."""
    for spec in parse_spec_input(load_json_path(args.input_path)):
        prompt_row: dict[str, object] = {
            "id": spec.id,
            "name": spec.name,
            "instruct": compose_instruct(spec.voice, args.profile),
            "language": spec.language,
        }
        if spec.text:
            prompt_row["text"] = spec.text
        print(json.dumps(prompt_row, ensure_ascii=False))
    return 0
