"""Ephemeral acceptance server for the bundled voices studio."""

import argparse
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

import uvicorn

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tests"))

from helpers import LONG_MOCK_AUDIO, MOCK_AUDIO, seed_clone_voice, seed_voice  # noqa: E402

from voices.domain.create_contracts import TranscriptionDraft  # noqa: E402
from voices.edge.app import create_edge_app, resolve_web_dist  # noqa: E402
from voices.util.slug import voice_id_from_name  # noqa: E402
from voices.workflow.clone_voice import PreparedCloneReview  # noqa: E402


def build_app(fixture: str):
    fixture_root = REPO_ROOT / ".tmp" / "ui-fixture" / fixture
    shutil.rmtree(fixture_root, ignore_errors=True)
    library = fixture_root / "voices"
    out_dir = fixture_root / "outputs"
    library.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    if fixture == "many":
        for index in range(44):
            seed_voice(library, f"batch_voice_{index:02d}")
    elif fixture in {"seeded", "slow-design"}:
        seed_voice(library, "noir_narrator")
        seed_voice(library, "radio_spark")
        seed_clone_voice(library, "matteo")

    app = create_edge_app(library=library, out_dir=out_dir, web_dist=resolve_web_dist())
    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixture", choices=["empty", "seeded", "slow-design", "many"], required=True)
    args = parser.parse_args()

    def mock_prepare_clone_review(*, request, **_: object) -> PreparedCloneReview:
        requested_name = request.requested_name or request.fallback_name
        return PreparedCloneReview(
            draft=TranscriptionDraft(
                transcript="Hello from local STT.",
                language="English",
                duration_seconds=4.0,
                segments=[],
            ),
            normalized_audio=LONG_MOCK_AUDIO,
            suggested_voice_id=voice_id_from_name(requested_name),
        )

    def mock_design_reference_audio(*_args: object, **_kwargs: object):
        if args.fixture == "slow-design":
            time.sleep(1.0)
        return MOCK_AUDIO, 24000

    with (
        patch("voices.workflow.design_voice.design_reference_audio", side_effect=mock_design_reference_audio),
        patch("voices.workflow.synthesize_voice.synthesize_reference_voice", return_value=(MOCK_AUDIO, 24000)),
        patch("voices.edge.service.prepare_clone_review", side_effect=mock_prepare_clone_review),
        patch("voices.workflow.clone_voice.convert_to_reference_audio", return_value=LONG_MOCK_AUDIO),
    ):
        uvicorn.run(build_app(args.fixture), host="127.0.0.1", port=args.port, log_level="warning", proxy_headers=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
