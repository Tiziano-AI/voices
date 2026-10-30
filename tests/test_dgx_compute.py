"""Explicit selection, source-shaped SSH custody and recovery; no inference."""

import hashlib
import io
import json
import tarfile
from dataclasses import replace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from helpers import seed_voice

from voices.adapter import dgx_compute
from voices.compute import DGX_MODELS, ComputeSelection
from voices.domain.errors import GenerationError, InvalidInputError
from voices.edge.app import create_edge_app
from voices.runtime_identity import RuntimeIdentity
from voices.workflow import synthesize_voice


def remote_runtime(invocation="a" * 32, operation="base"):
    model, revision = DGX_MODELS[operation]
    return RuntimeIdentity(
        python="3.12",
        executable="/occurrence/tts/bin/python",
        platform="Linux-aarch64",
        voices_version="fixture",
        source_sha256="b" * 64,
        source_scope="dgx-worker-source-at-execution",
        packages={"torch": "retained"},
        compute={
            "backend": "dgx",
            "invocation": invocation,
            "model_id": model,
            "model_revision": revision,
            "image": dgx_compute.IMAGE,
            "cuda": {"cuda_compiled": "13.0"},
            "controls": {"offline": True},
        },
    )


def test_default_is_mlx_and_remote_selection_never_borrows_mlx_revision(tmp_path):
    assert ComputeSelection().backend == "mlx"
    selection = ComputeSelection("dgx", "dgx-b", state_root=tmp_path)
    assert selection.model("base") == DGX_MODELS["base"]
    with pytest.raises(InvalidInputError, match="retained pinned"):
        selection.model("base", "a" * 40)
    with pytest.raises(InvalidInputError, match="SSH options"):
        ComputeSelection(ssh_host="dgx-b")
    with pytest.raises(InvalidInputError, match="alias"):
        ComputeSelection("dgx", "-oProxyCommand=bad")
    assert selection.describe()["remote_readiness_observed"] is False


def test_uncertain_submission_retains_exact_inputs_and_never_replays(tmp_path, monkeypatch):
    selection = ComputeSelection("dgx", "dgx-b", state_root=tmp_path)
    calls = []

    def ssh(_selection, command, data=None):
        calls.append((command, data))
        if data is None:
            return b"/home/synthetic\n"
        raise GenerationError("synthetic lost acknowledgement")

    monkeypatch.setattr(dgx_compute, "_ssh", ssh)
    with pytest.raises(GenerationError, match="no replay or MLX fallback"):
        dgx_compute.execute(
            selection,
            "base",
            language="Italian",
            text="Nuova frase.",
            audio=b"captured exact WAV",
            audio_format="wav",
            reference_text="Testo approvato.",
        )
    assert len(calls) == 2 and sum(data is not None for _, data in calls) == 1
    (root,) = tmp_path.iterdir()
    request = json.loads((root / "request.json").read_bytes())
    assert request["audio_sha256"] == hashlib.sha256(b"captured exact WAV").hexdigest()
    assert request["reference_text_sha256"] == hashlib.sha256("Testo approvato.".encode()).hexdigest()
    assert (root / "submission-intent.json").is_file() and not (root / "submitted.json").exists()
    with tarfile.open(fileobj=io.BytesIO(calls[1][1])) as archive:
        assert archive.extractfile("input.audio").read() == b"captured exact WAV"
        assert archive.extractfile("request.json").read() == (root / "request.json").read_bytes()
    assert "mkdir /home/synthetic/.local/state/voices/compute/" in calls[1][0]


def test_audio_only_asr_rejects_expected_text_before_ssh(tmp_path, monkeypatch):
    ssh = MagicMock(side_effect=AssertionError("must not transmit"))
    monkeypatch.setattr(dgx_compute, "_ssh", ssh)
    with pytest.raises(InvalidInputError, match="Audio-only"):
        dgx_compute.execute(
            ComputeSelection("dgx", "dgx-b", state_root=tmp_path),
            "asr",
            language="Italian",
            audio=b"audio",
            text="Not permitted",
        )
    ssh.assert_not_called()


def recovery_fixture(tmp_path, monkeypatch):
    invocation = "a" * 32
    selection = ComputeSelection("dgx", "dgx-b", state_root=tmp_path)
    root = tmp_path / invocation
    root.mkdir()
    request = {
        "operation": "asr",
        "model_id": DGX_MODELS["asr"][0],
        "revision": DGX_MODELS["asr"][1],
        "image": dgx_compute.IMAGE,
    }
    (root / "request.json").write_text(json.dumps(request))
    (root / "selection.json").write_text(json.dumps({"host": "dgx-b", "ssh_config": None, "remote": "/same/id"}))
    (root / "submission-intent.json").write_text(json.dumps({"worker_bundle_sha256": "b" * 64}))
    result = {
        "request_sha256": hashlib.sha256((root / "request.json").read_bytes()).hexdigest(),
        "runtime": remote_runtime(operation="asr").model_dump(mode="json"),
        "transcript": "Synthetic.",
    }
    calls = []

    def ssh(_selection, command, data=None):
        calls.append(command)
        if " inspect " in command:
            return b'{"state":"completed","owned_container_absent":true}'
        assert command == "cat /same/id/result.json"
        return json.dumps(result).encode()

    monkeypatch.setattr(dgx_compute, "_ssh", ssh)
    return selection, invocation, result, calls


def test_recovery_collects_same_occurrence_without_publication_or_submission(tmp_path, monkeypatch):
    selection, invocation, _result, calls = recovery_fixture(tmp_path, monkeypatch)
    assert dgx_compute.recover_invocation(selection, invocation).payload["transcript"] == "Synthetic."
    assert all(" start " not in command and "tar " not in command for command in calls)
    assert sorted(path.name for path in tmp_path.iterdir()) == [invocation]
    with pytest.raises(InvalidInputError, match="original SSH"):
        dgx_compute.inspect_invocation(replace(selection, ssh_host="other"), invocation)


def test_collection_rejects_corrupt_existing_receipt_instead_of_skipping_it(tmp_path, monkeypatch):
    selection, invocation, _result, _calls = recovery_fixture(tmp_path, monkeypatch)
    path = tmp_path / invocation / "result.json"
    path.write_bytes(b"interrupted partial result")
    with pytest.raises(GenerationError, match="differs from fetched receipt"):
        dgx_compute.recover_invocation(selection, invocation)
    assert path.read_bytes() == b"interrupted partial result"


def test_interrupted_collection_publishes_no_partial_final_and_recovers_same_bytes(tmp_path, monkeypatch):
    path = tmp_path / "output.wav"
    link = dgx_compute.os.link
    monkeypatch.setattr(dgx_compute.os, "link", MagicMock(side_effect=OSError("synthetic full disk")))
    with pytest.raises(OSError, match="full disk"):
        dgx_compute._publish(path, b"complete retained bytes")
    assert not path.exists() and list(tmp_path.iterdir()) == []
    monkeypatch.setattr(dgx_compute.os, "link", link)
    dgx_compute._publish(path, b"complete retained bytes")
    dgx_compute._publish(path, b"complete retained bytes")
    assert path.read_bytes() == b"complete retained bytes"
    with pytest.raises(GenerationError):
        dgx_compute._publish(path, b"different")


@pytest.mark.parametrize(
    "field,value", [("invocation", "c" * 32), ("image", "different"), ("model_revision", "d" * 40)]
)
def test_recovery_rejects_foreign_execution_provenance(tmp_path, monkeypatch, field, value):
    selection, invocation, result, _calls = recovery_fixture(tmp_path, monkeypatch)
    result["runtime"]["compute"][field] = value
    with pytest.raises(GenerationError):
        dgx_compute.recover_invocation(selection, invocation)


def test_studio_dgx_preview_binds_reference_and_saves_exact_preview_once(tmp_path, monkeypatch):
    library, outputs = tmp_path / "library", tmp_path / "outputs"
    seed_voice(library)
    runtime = remote_runtime()
    execute = MagicMock(
        return_value=dgx_compute.ComputeResult({}, runtime, np.ones(2400, dtype=np.float32) * 0.1, 24000)
    )
    monkeypatch.setattr(synthesize_voice, "execute", execute)
    monkeypatch.setattr(
        synthesize_voice, "synthesize_reference_voice", MagicMock(side_effect=AssertionError("MLX fallback"))
    )
    app = create_edge_app(library=library, out_dir=outputs, web_dist=None, compute=ComputeSelection("dgx", "dgx-b"))
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/ui-config").json()["compute_backend"] == "dgx"
        clip = client.post("/api/preview", json={"voice_id": "test_voice", "text": "Una nuova frase."}).json()
        wav = client.get(clip["audio_url"]).content
        url = f"/api/previews/{clip['token']}/export"
        first, second = client.post(url), client.post(url)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert client.get(first.json()["audio_url"]).content == wav
        assert first.json()["record"]["runtime"] == runtime.model_dump(mode="json")
    execute.assert_called_once()
    assert execute.call_args.kwargs["audio"] == (library / "test_voice/reference.wav").read_bytes()
    assert execute.call_args.kwargs["reference_text"] == "Hello world."
    assert len(list(outputs.rglob("*.wav"))) == len(list(outputs.rglob("*.json"))) == 1
