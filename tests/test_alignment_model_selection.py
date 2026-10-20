"""Exercise actual MLX Audio dispatch, stopping before model allocation or weights."""

import hashlib
import json
from pathlib import Path

import pytest
from mlx_audio.stt import utils
from mlx_audio.stt.models.qwen3_asr.qwen3_asr import Model as AsrModel
from mlx_audio.stt.models.qwen3_forced_aligner import Model as AlignerModel

from voices.adapter import mlx_align

PINNED_REVISION = "53c8c0e46733eec430e4b53dd6471d0e5dee45f8"
MODEL_ID = "mlx-community/Qwen3-ForcedAligner-0.6B-bf16"
FIXTURE = Path(__file__).parent / "fixtures" / "qwen3_forced_aligner_53c8c0e_config.json"


class ArchitectureSelected(Exception):
    """Stop at the constructor boundary, before any model memory or weights."""


def test_pinned_snapshot_dispatch_selects_aligner_explicitly(monkeypatch, tmp_path):
    # Published config.json from this immutable revision, with only a final
    # newline added by the source fixture. Keep the real hub path shape.
    config_bytes = FIXTURE.read_bytes()
    assert hashlib.sha256(config_bytes.removesuffix(b"\n")).hexdigest() == (
        "dffdf2e17fa13effca4b165540c8eeea6d3f3211dcdb6c21978e68578460858d"
    )
    config = json.loads(config_bytes)
    assert config["model_type"] == "qwen3_asr"
    assert config["thinker_config"]["model_type"] == "qwen3_forced_aligner"
    snapshot = tmp_path / "hub" / "models--mlx-community--Qwen3-ForcedAligner-0.6B-bf16" / "snapshots" / PINNED_REVISION
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_bytes(config_bytes)

    def stop_asr(self, config):
        raise ArchitectureSelected("asr")

    def stop_aligner(self, config):
        raise ArchitectureSelected("aligner")

    def resolve(model_id, revision):
        assert (model_id, revision) == (MODEL_ID, PINNED_REVISION)
        return snapshot

    monkeypatch.setattr(AsrModel, "__init__", stop_asr)
    monkeypatch.setattr(AlignerModel, "__init__", stop_aligner)
    monkeypatch.setattr(mlx_align, "resolve_model_snapshot", resolve)

    # Preserve the observed failed dispatch as a countercase. Neither call
    # mocks load/config parsing/architecture resolution or loads model weights.
    with pytest.raises(ArchitectureSelected, match="^asr$"):
        utils.load(snapshot, strict=True)
    with pytest.raises(ArchitectureSelected, match="^aligner$"):
        mlx_align._load_runtime(MODEL_ID, PINNED_REVISION)
    assert hashlib.sha256((snapshot / "config.json").read_bytes()).digest() == hashlib.sha256(config_bytes).digest()
