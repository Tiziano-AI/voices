"""CLI adapter for the voices prompt workbench."""

from __future__ import annotations

import sys

from .cli_parser import build_parser
from .contracts import WorkbenchError


def main() -> int:
    """Run the workbench CLI."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except WorkbenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
