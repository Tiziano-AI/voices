"""Immutable selection and model-cache contracts, without network or inference."""

from unittest.mock import MagicMock

import pytest

from voices import config
from voices.adapter import mlx_qwen, mlx_stt, model_snapshot
from voices.adapter.mlx_runtime import serialized_mlx_runtime
from voices.domain.errors import GenerationError, InvalidInputError


@pytest.mark.parametrize("revision", ["", "main", "v1.0", "a" * 39, "a" * 41, "g" * 40, " a" + "0" * 38])
def test_invalid_revision_is_rejected_before_hub_access(monkeypatch, revision):
    download = MagicMock(side_effect=AssertionError("must not contact Hub"))
    monkeypatch.setattr(model_snapshot._hub, "snapshot_download", download)
    with pytest.raises(InvalidInputError, match="40-character"):
        model_snapshot.resolve_model_snapshot("test/model", revision)
    download.assert_not_called()


def test_snapshot_uses_exact_commit_and_leaves_mutable_ref_alone(tmp_path, monkeypatch):
    model = tmp_path / "models--test--model"
    snapshot = model / "snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    ref = model / "refs" / "main"
    ref.parent.mkdir()
    ref.write_text("b" * 40)
    download = MagicMock(return_value=str(snapshot))
    monkeypatch.setattr(model_snapshot._hub, "snapshot_download", download)
    assert model_snapshot.resolve_model_snapshot("test/model", "A" * 40) == snapshot
    download.assert_called_once_with(repo_id="test/model", revision="a" * 40)
    assert ref.read_text() == "b" * 40


@pytest.mark.parametrize("relative", ["snapshots/" + "b" * 40, "refs/" + "a" * 40, "snapshots/missing"])
def test_wrong_snapshot_is_rejected(tmp_path, monkeypatch, relative):
    snapshot = tmp_path / relative
    snapshot.mkdir(parents=True)
    monkeypatch.setattr(model_snapshot._hub, "snapshot_download", lambda **_kwargs: str(snapshot))
    with pytest.raises(GenerationError, match="requested immutable snapshot"):
        model_snapshot.resolve_model_snapshot("test/model", "a" * 40)


def test_missing_offline_revision_becomes_product_generation_error(monkeypatch):
    download = MagicMock(side_effect=FileNotFoundError("revision not cached while offline"))
    monkeypatch.setattr(model_snapshot._hub, "snapshot_download", download)
    with pytest.raises(GenerationError, match="revision not cached while offline"):
        model_snapshot.resolve_model_snapshot("test/model", "a" * 40)


@pytest.mark.parametrize("adapter", [mlx_qwen, mlx_stt])
def test_runtime_cache_separates_model_and_revision(monkeypatch, adapter):
    monkeypatch.setattr(adapter, "_runtime_cache", {})
    load = MagicMock(side_effect=lambda *_args: MagicMock())
    monkeypatch.setattr(adapter, "_load_runtime", load)
    with serialized_mlx_runtime():
        first = adapter._get_runtime("test/model", "a" * 40)
        assert adapter._get_runtime("test/model", "A" * 40) is first
        assert adapter._get_runtime("test/model", "b" * 40) is not first
        assert adapter._get_runtime("test/other-model", "a" * 40) is not first
    assert load.call_count == 3


def test_all_configured_models_use_complete_commit_revisions():
    for revision in (
        config.BASE_MODEL_REVISION,
        config.VOICE_DESIGN_MODEL_REVISION,
        config.STT_MODEL_REVISION,
        config.ALIGNER_MODEL_REVISION,
    ):
        assert model_snapshot.require_model_revision(revision) == revision
