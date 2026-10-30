"""Dependency-separated SSH worker custody; no Voices/MLX install on DGX.

The existing DGX lifecycle must admit a vacant lane first. This worker never
stops another container, changes a serving profile or installs anything.
"""

import fcntl
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

IMAGE: str = "nvcr.io/nvidia/vllm@sha256:cb38bbefdbc3e9fe045f931dd72cbd58cd48985c7e09916bcc6c15c10f39b929"


def save(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def identity(pid: int) -> dict[str, Any]:
    return {
        "pid": pid,
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "ticks": Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19],
    }


def docker(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["sudo", "-n", "docker", *args], capture_output=True)


def inspect(name: str) -> dict[str, Any] | None:
    result = docker("inspect", name)
    if result.returncode:
        if b"no such" not in result.stderr.lower():
            raise RuntimeError("Cannot inspect container identity")
        return None
    return json.loads(result.stdout)[0]


def state(root: Path) -> dict[str, Any]:
    if (root / "terminal.json").is_file():
        return read(root / "terminal.json")
    if (root / "owner.json").is_file():
        expected = read(root / "owner.json")
        try:
            alive = identity(expected["pid"]) == expected
        except FileNotFoundError:
            alive = False
        return {
            "state": "running" if alive else "unknown",
            "owner_alive": alive,
            "invocation": root.name,
            "automatic_replay": False,
        }
    return {"state": "unknown", "invocation": root.name, "automatic_replay": False}


def owned_container(root: Path, name: str, digest: str) -> dict[str, Any] | None:
    """An uncertain create is reconciled against this invocation's durable intent."""
    container = inspect(name)
    if container is not None:
        labels: dict[str, Any] = container["Config"].get("Labels") or {}
        if labels.get("voices.invocation") != root.name or labels.get("voices.request") != digest:
            raise RuntimeError("Container identity is not owned; integration required")
        receipt = root / "container.json"
        if receipt.is_file() and read(receipt)["id"] != container["Id"]:
            raise RuntimeError("Acquired container identity changed; integration required")
    return container


def settle_container(root: Path, digest: str) -> int | None:
    """Reconcile only this durable create intent, including lost cleanup receipts."""
    intent_path = root / "create-intent.json"
    if not intent_path.is_file():
        return None  # This invocation acquired no container.
    intent = read(intent_path)
    if intent != {"name": "voices-" + root.name, "invocation": root.name, "request_sha256": digest}:
        raise RuntimeError("Create intent identity changed; integration required")
    receipt = root / "container.json"
    target = read(receipt)["id"] if receipt.is_file() else intent["name"]
    container = owned_container(root, target, digest)
    exit_path = root / "child-exit.json"
    if container is not None:
        cid = container["Id"]
        if container["State"]["Running"]:
            if docker("wait", cid).returncode:
                raise RuntimeError("Owned child settlement unknown")
            container = owned_container(root, cid, digest)
            if container is None or container["State"]["Running"]:
                raise RuntimeError("Owned child terminal state unverified")
        exit_receipt: dict[str, Any] = {
            "id": cid,
            "request_sha256": digest,
            "exit_code": container["State"]["ExitCode"],
        }
        if exit_path.is_file():
            if read(exit_path) != exit_receipt:
                raise RuntimeError("Owned child exit identity changed")
        else:
            # Persist before removal: recovery can distinguish removed from never-settled.
            save(exit_path, exit_receipt)
        if docker("rm", cid).returncode or inspect(cid) is not None:
            raise RuntimeError("Owned container absence unverified")
    if exit_path.is_file():
        exited = read(exit_path)
        if exited["request_sha256"] != digest or (receipt.is_file() and read(receipt)["id"] != exited["id"]):
            raise RuntimeError("Owned child exit receipt differs from acquired identity")
        return exited["exit_code"]
    return None


def publish_terminal(root: Path, code: int | None, seconds: float) -> None:
    outcome = "completed" if code == 0 and (root / "result.json").is_file() else "failed"
    if code is None and (root / "create-intent.json").is_file():
        outcome = "unknown"
    save(
        root / "terminal.json",
        {
            "state": outcome,
            "invocation": root.name,
            "exit_code": code,
            "owned_container_absent": True,
            "operation_seconds": seconds,
            "automatic_replay": False,
        },
    )


def settle(root: Path) -> None:
    """Explicit recovery after owner loss; never create/start/resubmit inference."""
    if (root / "terminal.json").is_file():
        return
    if state(root).get("owner_alive"):
        raise RuntimeError("Original owner is alive; observe it instead of taking custody")
    with (root.parent / "admission.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        started = time.monotonic()
        digest = hashlib.sha256((root / "request.json").read_bytes()).hexdigest()
        code = settle_container(root, digest)
        publish_terminal(root, code, time.monotonic() - started)


def run(root: Path) -> None:
    request = read(root / "request.json")
    digest = hashlib.sha256((root / "request.json").read_bytes()).hexdigest()
    if request["invocation"] != root.name:
        raise ValueError("Invocation identity mismatch")
    save(root / "owner.json", identity(os.getpid()))
    started = time.monotonic()
    name = "voices-" + root.name
    creation_intent = False
    code = None
    lock = None
    try:
        lock = (root.parent / "admission.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if inspect(name) is not None:
            raise RuntimeError("Preexisting container: not acquired by this invocation")
        retained = inspect("dgx-inference")
        if retained is not None and retained["State"]["Running"]:
            raise RuntimeError("DGX lifecycle has not admitted a vacant lane")
        gpu = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], capture_output=True, check=True
        )
        if gpu.stdout.strip():
            raise RuntimeError("Foreign GPU work: not admitted")
        image = docker("image", "inspect", IMAGE)
        if image.returncode or json.loads(image.stdout)[0]["Architecture"] != "arm64":
            raise RuntimeError("Retained CUDA image unavailable")
        overlay = Path.home() / ".local/state/dgx/audio-env-probe-20261027"
        model_root = Path.home() / ".local/share/dgx/models/hub" / ("models--" + request["model_id"].replace("/", "--"))
        if not (model_root / "snapshots" / request["revision"] / "config.json").is_file():
            raise RuntimeError("Retained pinned checkpoint unavailable; no download")
        phase = "tts" if request["operation"] in ("design", "base") else "asr"
        args = [
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            "voices.invocation=" + root.name,
            "--label",
            "voices.request=" + digest,
            "--read-only",
            "--network",
            "none",
            "--gpus",
            "all",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory",
            "64g",
            "--memory-swap",
            "64g",
            "--cpus",
            "12",
            "--pids-limit",
            "512",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--tmpfs",
            "/tmp:rw,exec,nosuid,nodev,size=1g",
        ]
        for source, target, readonly in (
            (overlay, "/occurrence", True),
            (root, "/job", False),
            (model_root, "/models", True),
        ):
            args += ["--mount", f"type=bind,source={source},target={target}" + (",readonly" if readonly else "")]
        for key, value in {
            "HOME": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "XDG_CACHE_HOME": "/job/cache",
            "HF_HOME": "/job/cache/hf",
            "NUMBA_CACHE_DIR": "/job/cache/numba",
            "OMP_NUM_THREADS": "8",
        }.items():
            args += ["--env", key + "=" + value]
        args += ["--entrypoint", f"/occurrence/{phase}/bin/python", IMAGE, "/job/dgx_engine.py"]
        save(root / "create-intent.json", {"name": name, "invocation": root.name, "request_sha256": digest})
        creation_intent = True
        created = docker(*args)
        container = owned_container(root, name, digest)
        if created.returncode or container is None:
            raise RuntimeError("Container creation failed or uncertain; retained custody")
        cid = container["Id"]
        save(root / "container.json", {"id": cid, "request_sha256": digest})
        with (root / "engine.stdout").open("xb") as output, (root / "engine.stderr").open("xb") as errors:
            code = subprocess.run(["sudo", "-n", "docker", "start", "-a", cid], stdout=output, stderr=errors).returncode
    except BaseException as exc:
        save(root / "attention.json", {"exception_type": type(exc).__name__, "automatic_replay": False})
    finally:
        try:
            if creation_intent:
                code = settle_container(root, digest)
            publish_terminal(root, code, time.monotonic() - started)
        finally:
            if lock is not None:
                lock.close()


def main() -> None:
    os.umask(0o077)
    operation, raw_root = sys.argv[1:]
    root = Path(raw_root).resolve()
    if (
        root.parent != Path.home() / ".local/state/voices/compute"
        or len(root.name) != 32
        or any(c not in "0123456789abcdef" for c in root.name)
    ):
        raise ValueError("Invalid owned invocation root")
    if operation == "start":
        save(root / "launch-intent.json", {"invocation": root.name, "automatic_replay": False})
        command = shlex.join([sys.executable, str(root / "dgx_worker.py"), "run", str(root)])
        command += " >" + shlex.quote(str(root / "worker.stdout")) + " 2>" + shlex.quote(str(root / "worker.stderr"))
        subprocess.run(["tmux", "new-session", "-d", "-s", "voices-" + root.name, command], check=True)
    elif operation == "run":
        run(root)
    elif operation == "inspect":
        print(json.dumps(state(root)))
    elif operation == "settle":
        settle(root)
        print(json.dumps(state(root)))
    elif operation == "wait":
        while state(root)["state"] in ("unknown", "running"):
            # Wait only while the exact tmux owner survives; unknown is never replayed.
            if subprocess.run(["tmux", "has-session", "-t", "voices-" + root.name], capture_output=True).returncode:
                if not (root / "terminal.json").is_file():
                    raise RuntimeError("Invocation custody requires inspection")
                break
            time.sleep(1)
        print(json.dumps(state(root)))
    else:
        raise ValueError("Unsupported worker operation")


if __name__ == "__main__":
    main()
