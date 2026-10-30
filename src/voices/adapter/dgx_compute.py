"""Four complete-result operations over existing authenticated SSH, no listener.

Each request has private local custody before transmission. An uncertain SSH
submission is never retried: recovery queries that same invocation only.
"""

import hashlib
import io
import json
import os
import shlex
import subprocess
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import numpy as np

from voices.adapter.dgx_worker import IMAGE
from voices.compute import ComputeSelection, Operation
from voices.domain.errors import GenerationError, InvalidInputError
from voices.runtime_identity import RuntimeIdentity


@dataclass(frozen=True, slots=True)
class ComputeResult:
    """Generation metadata belongs to the remote worker, not the MLX client."""

    payload: dict[str, Any]
    runtime: RuntimeIdentity
    audio: np.ndarray | None = None
    sample_rate: int | None = None


def _save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(path: Path, raw: bytes) -> None:
    """Atomic no-clobber collection; existing custody must match fetched bytes."""
    if path.exists():
        if path.read_bytes() != raw:
            raise GenerationError("Retained compute collection differs from fetched receipt; preserve for inspection.")
        return
    temporary = path.with_name(path.name + "." + uuid4().hex + ".partial")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise GenerationError("Concurrent retained collection differs; integration required.") from None
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _ssh(selection: ComputeSelection, command: str, data: bytes | None = None) -> bytes:
    args = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
    if selection.ssh_config is not None:
        args += ["-F", str(selection.ssh_config.expanduser().resolve())]
    args += [str(selection.ssh_host), command]
    result = subprocess.run(args, input=data, capture_output=True, check=False)
    if result.returncode:
        raise GenerationError(
            "DGX SSH operation did not settle locally; inspect the retained invocation, never replay."
        )
    return result.stdout


def _directory(selection: ComputeSelection, invocation: str) -> Path:
    if len(invocation) != 32 or any(c not in "0123456789abcdef" for c in invocation):
        raise InvalidInputError("Invalid compute invocation identity.")
    return selection.state_root.expanduser().resolve() / invocation


def inspect_invocation(selection: ComputeSelection, invocation: str) -> dict[str, object]:
    """Read the same remote occurrence; this never submits inference."""
    directory = _directory(selection, invocation)
    local = json.loads((directory / "selection.json").read_bytes())
    if local["host"] != selection.ssh_host or local["ssh_config"] != (
        str(selection.ssh_config.expanduser().resolve()) if selection.ssh_config else None
    ):
        raise InvalidInputError("Recovery must use the original SSH selection.")
    command = f"python3 {shlex.quote(local['remote'] + '/dgx_worker.py')} inspect {shlex.quote(local['remote'])}"
    return json.loads(_ssh(selection, command))


def recover_invocation(selection: ComputeSelection, invocation: str) -> ComputeResult:
    """Collect a settled result without regeneration or automatic publication."""
    directory = _directory(selection, invocation)
    state = inspect_invocation(selection, invocation)
    if state.get("state") == "unknown":
        local = json.loads((directory / "selection.json").read_bytes())
        command = f"python3 {shlex.quote(local['remote'] + '/dgx_worker.py')} settle {shlex.quote(local['remote'])}"
        state = json.loads(_ssh(selection, command))
    if state.get("state") != "completed" or not state.get("owned_container_absent"):
        raise GenerationError(f"DGX invocation {invocation} is not completed/settled; no replay was attempted.")
    local = json.loads((directory / "selection.json").read_bytes())
    result_bytes = _ssh(selection, "cat " + shlex.quote(local["remote"] + "/result.json"))
    result = json.loads(result_bytes)
    request = json.loads((directory / "request.json").read_bytes())
    if result["request_sha256"] != hashlib.sha256((directory / "request.json").read_bytes()).hexdigest():
        raise GenerationError("DGX result does not identify this exact request.")
    runtime = RuntimeIdentity.model_validate(result["runtime"])
    if runtime.source_scope != "dgx-worker-source-at-execution" or runtime.compute is None:
        raise GenerationError("DGX result is missing remote execution provenance.")
    intent = json.loads((directory / "submission-intent.json").read_bytes())
    if runtime.source_sha256 != intent["worker_bundle_sha256"]:
        raise GenerationError("DGX result does not identify the exact submitted worker sources.")
    if (runtime.compute.model_id, runtime.compute.model_revision) != (request["model_id"], request["revision"]):
        raise GenerationError("DGX result checkpoint differs from the selected request.")
    if runtime.compute.invocation != invocation or runtime.compute.image != request["image"]:
        raise GenerationError("DGX result invocation or CUDA image differs from this request.")
    audio = None
    rate = None
    if request["operation"] in ("design", "base"):
        wav = _ssh(selection, "cat " + shlex.quote(local["remote"] + "/output.wav"))
        if hashlib.sha256(wav).hexdigest() != result["audio_sha256"]:
            raise GenerationError("DGX WAV identity mismatch.")
        from scipy.io import wavfile

        read_wav = cast(Callable[[io.BytesIO], tuple[int, np.ndarray]], getattr(wavfile, "read"))
        rate, audio = read_wav(io.BytesIO(wav))
        if audio.dtype.kind != "f" or rate != result["sample_rate"]:
            raise GenerationError("DGX complete WAV encoding or sample rate differs from its receipt.")
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim != 1 or not audio.size or not bool(np.isfinite(audio).all()):
            raise GenerationError("DGX returned an invalid complete mono WAV.")
        _publish(directory / "output.wav", wav)
    _publish(directory / "result.json", result_bytes)
    return ComputeResult(result, runtime, audio, rate)


def execute(
    selection: ComputeSelection,
    operation: Operation,
    *,
    language: str,
    text: str | None = None,
    instruct: str | None = None,
    audio: bytes | None = None,
    audio_format: str | None = None,
    reference_text: str | None = None,
    revision: str | None = None,
) -> ComputeResult:
    """Submit once, wait under remote tmux custody, then collect exact output."""
    if selection.backend != "dgx":
        raise InvalidInputError("The SSH executor requires explicit DGX selection.")
    invocation = uuid4().hex
    directory = _directory(selection, invocation)
    directory.mkdir(parents=True, mode=0o700)
    model, pinned = selection.model(operation, revision)
    request: dict[str, object] = {
        "invocation": invocation,
        "operation": operation,
        "model_id": model,
        "revision": pinned,
        "voices_version": version("voices"),
        "image": IMAGE,
        "language": language,
        "text": text,
        "instruct": instruct,
        "reference_text": reference_text,
        "audio_format": audio_format,
        "audio_sha256": hashlib.sha256(audio).hexdigest() if audio else None,
        "reference_text_sha256": hashlib.sha256(reference_text.encode()).hexdigest() if reference_text else None,
    }
    if operation == "asr" and any(v is not None for v in (text, instruct, reference_text)):
        raise InvalidInputError("Audio-only ASR cannot receive expected text.")
    _save(directory / "request.json", request)
    # Remote HOME is resolved by its own interpreter, not assumed from Mac HOME.
    remote_root = _ssh(selection, "python3 -c 'from pathlib import Path; print(Path.home())'").decode().strip()
    remote = remote_root + "/.local/state/voices/compute/" + invocation
    _save(
        directory / "selection.json",
        {
            "host": selection.ssh_host,
            "remote": remote,
            "ssh_config": str(selection.ssh_config.expanduser().resolve()) if selection.ssh_config else None,
        },
    )
    payload = {"request.json": (directory / "request.json").read_bytes()}
    if audio is not None:
        payload["input.audio"] = audio
    for name in ("dgx_worker.py", "dgx_engine.py"):
        payload[name] = Path(__file__).with_name(name).read_bytes()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        for name, raw in payload.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(raw), 0o600
            stream.addfile(info, io.BytesIO(raw))
    _save(
        directory / "submission-intent.json",
        {
            "invocation": invocation,
            "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in payload.items()},
            "worker_bundle_sha256": hashlib.sha256(payload["dgx_worker.py"] + payload["dgx_engine.py"]).hexdigest(),
        },
    )
    command = "set -eu; umask 077; mkdir -p " + shlex.quote(remote_root + "/.local/state/voices/compute")
    command += "; mkdir " + shlex.quote(remote) + "; tar --keep-old-files -xf - -C " + shlex.quote(remote)
    command += "; python3 " + shlex.quote(remote + "/dgx_worker.py") + " start " + shlex.quote(remote)
    try:
        _ssh(selection, command, archive.getvalue())
        _save(directory / "submitted.json", {"invocation": invocation})
        _ssh(selection, "python3 " + shlex.quote(remote + "/dgx_worker.py") + " wait " + shlex.quote(remote))
        return recover_invocation(selection, invocation)
    except (OSError, ValueError, GenerationError) as exc:
        raise GenerationError(
            f"DGX invocation {invocation} requires inspection/recovery in {directory}; no replay or MLX fallback."
        ) from exc
