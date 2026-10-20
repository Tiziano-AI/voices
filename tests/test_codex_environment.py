"""Contract tests for the checked-in Codex App local environment."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT_PATH = REPO_ROOT / ".codex" / "environments" / "environment.toml"


def test_codex_environment_defines_voice_lifecycle_actions() -> None:
    """Keep Codex top-bar actions aligned with the documented product lifecycle."""
    environment = tomllib.loads(ENVIRONMENT_PATH.read_text(encoding="utf-8"))

    assert environment["version"] == 1
    assert environment["name"] == "voices"
    assert environment["setup"]["darwin"]["script"].strip().splitlines() == [
        "pnpm --dir web install --frozen-lockfile",
        "pnpm --dir web build",
        "uv sync --locked",
    ]

    actions = environment["actions"]
    assert actions == [
        {
            "name": "Setup",
            "icon": "tool",
            "command": "pnpm --dir web install --frozen-lockfile && pnpm --dir web build && uv sync --locked",
            "platform": "darwin",
        },
        {
            "name": "Run Studio",
            "icon": "run",
            "command": "uv run voices ui",
            "platform": "darwin",
        },
        {
            "name": "Doctor",
            "icon": "tool",
            "command": "uv run voices doctor",
            "platform": "darwin",
        },
        {
            "name": "Build UI",
            "icon": "tool",
            "command": "pnpm --dir web build",
            "platform": "darwin",
        },
        {
            "name": "Gate",
            "icon": "test",
            "command": "uv run devtools/gate.py",
            "platform": "darwin",
        },
        {
            "name": "Python Tests",
            "icon": "test",
            "command": "uv run pytest tests/ -v",
            "platform": "darwin",
        },
        {
            "name": "Web Checks",
            "icon": "test",
            "command": "pnpm --dir web lint && pnpm --dir web build && pnpm --dir web acceptance",
            "platform": "darwin",
        },
        {
            "name": "List Voices",
            "icon": "tool",
            "command": "uv run voices list",
            "platform": "darwin",
        },
    ]
