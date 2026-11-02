"""Non-generating custody regressions at the real worker's Docker seam."""

import hashlib
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from voices.adapter import dgx_worker as worker
from voices.compute import DGX_MODELS


@pytest.fixture
def occurrence(tmp_path, monkeypatch):
    root = tmp_path / "compute" / ("a" * 32)
    root.mkdir(parents=True)
    root.chmod(0o700)
    model, revision = DGX_MODELS["design"]
    (root / "request.json").write_text(
        json.dumps({"invocation": root.name, "operation": "design", "model_id": model, "revision": revision})
    )
    (root / "request.json").chmod(0o600)
    checkpoint = (
        tmp_path / ".local/share/dgx/models/hub" / ("models--" + model.replace("/", "--")) / "snapshots" / revision
    )
    checkpoint.mkdir(parents=True)
    (checkpoint / "config.json").write_text("{}")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(worker, "identity", lambda pid: {"pid": pid, "boot": "fixture", "ticks": "1"})
    monkeypatch.setattr(worker.fcntl, "flock", lambda *_args: None)
    return root


def test_rejected_preexisting_candidate_is_never_acquired_or_removed(occurrence, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "inspect", lambda _name: {"Id": "preexisting"})
    monkeypatch.setattr(worker, "docker", lambda *args: calls.append(args))
    worker.run(occurrence)
    assert not calls and not (occurrence / "create-intent.json").exists()
    assert worker.read(occurrence / "terminal.json")["state"] == "failed"


@pytest.mark.parametrize("failure", ["uncertain_create", "receipt_failure"])
def test_uncertain_create_or_receipt_failure_settles_only_exact_owned_child(occurrence, monkeypatch, failure):
    created = False
    removed = False
    calls = []
    digest = hashlib.sha256((occurrence / "request.json").read_bytes()).hexdigest()
    container = {
        "Id": "exact-owned",
        "Config": {"Labels": {"voices.invocation": occurrence.name, "voices.request": digest}},
        "State": {"Running": False, "ExitCode": 1},
    }

    def inspect(name):
        if name == "dgx-inference":
            return {"State": {"Running": False}}
        return container if created and not removed else None

    def docker(*args):
        nonlocal created, removed
        calls.append(args)
        if args[0] == "image":
            return CompletedProcess(args, 0, b'[{"Architecture":"arm64"}]', b"")
        if args[0] == "create":
            assert (occurrence / "create-intent.json").is_file()
            created = True
            return CompletedProcess(args, 1 if failure == "uncertain_create" else 0, b"", b"")
        assert args == ("rm", "exact-owned")
        removed = True
        return CompletedProcess(args, 0, b"", b"")

    save = worker.save

    def fail_receipt(path, value):
        if path.name == "container.json" and failure == "receipt_failure":
            raise OSError("synthetic receipt failure")
        save(path, value)

    monkeypatch.setattr(worker, "save", fail_receipt)
    monkeypatch.setattr(worker, "inspect", inspect)
    monkeypatch.setattr(worker, "docker", docker)
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: CompletedProcess(args, 0, b"", b""))
    worker.run(occurrence)
    assert removed and calls[-1] == ("rm", "exact-owned")
    assert worker.read(occurrence / "terminal.json")["owned_container_absent"] is True
    worker.baseline_clearance(occurrence.parent)
    assert worker.read(occurrence.parent / "current.json")["invocation"] == occurrence.name


def test_replacement_identity_cannot_be_cleaned_up(occurrence, monkeypatch):
    digest = hashlib.sha256((occurrence / "request.json").read_bytes()).hexdigest()
    worker.save(occurrence / "container.json", {"id": "acquired"})
    monkeypatch.setattr(
        worker,
        "inspect",
        lambda _: {
            "Id": "replacement",
            "Config": {"Labels": {"voices.invocation": occurrence.name, "voices.request": digest}},
        },
    )
    with pytest.raises(RuntimeError, match="identity changed"):
        worker.owned_container(occurrence, "voices-" + occurrence.name, digest)


def test_busy_admission_records_failure_without_creating_a_child(occurrence, monkeypatch):
    def busy(*_args):
        raise BlockingIOError("another admitted operation")

    monkeypatch.setattr(worker.fcntl, "flock", busy)
    monkeypatch.setattr(worker, "inspect", lambda _: pytest.fail("must not touch containers"))
    worker.run(occurrence)
    assert worker.read(occurrence / "terminal.json")["state"] == "failed"
    assert not (occurrence / "create-intent.json").exists()
    assert not (occurrence.parent / "current.json").exists()


def test_clean_historical_use_clears_only_after_explicit_exact_legacy_reconciliation(occurrence):
    worker.publish_terminal(occurrence, 1, 0)
    with pytest.raises(RuntimeError, match="legacy custody"):
        worker.baseline_clearance(occurrence.parent)
    worker.reconcile_custody(occurrence.parent, [occurrence.name])
    worker.baseline_clearance(occurrence.parent)
    assert worker.read(occurrence.parent / "current.json")["state"] == "failed"


def test_legacy_unknown_or_inventory_gap_does_not_clear(occurrence):
    with pytest.raises(FileNotFoundError):
        worker.reconcile_custody(occurrence.parent, [occurrence.name])
    worker.save(occurrence / "create-intent.json", {})
    worker.publish_terminal(occurrence, None, 0)
    with pytest.raises(RuntimeError, match="requires settlement"):
        worker.reconcile_custody(occurrence.parent, [occurrence.name])
    with pytest.raises(RuntimeError, match="inventory differs"):
        worker.reconcile_custody(occurrence.parent, ["b" * 32])
    assert not (occurrence.parent / "current.json").exists()


def test_terminal_publication_loss_recovered_without_replay(occurrence):
    digest = hashlib.sha256((occurrence / "request.json").read_bytes()).hexdigest()
    worker.current_write(
        occurrence.parent, {"schema": 1, "invocation": occurrence.name, "request_sha256": digest, "state": "running"}
    )
    worker.publish_terminal(occurrence, 1, 0)
    with pytest.raises(RuntimeError, match="same-invocation"):
        worker.baseline_clearance(occurrence.parent)
    worker.settle(occurrence)
    worker.baseline_clearance(occurrence.parent)


def test_rejected_later_request_cannot_clear_or_replace_current_custody(occurrence, monkeypatch):
    original = {"schema": 1, "invocation": "b" * 32, "state": "running"}
    (occurrence.parent / original["invocation"]).mkdir(mode=0o700)
    worker.current_write(occurrence.parent, original)
    monkeypatch.setattr(worker, "inspect", lambda _: pytest.fail("must not inspect Docker"))
    worker.run(occurrence)
    assert worker.read(occurrence.parent / "current.json") == original
    with pytest.raises(RuntimeError, match="Another current"):
        worker.settle(occurrence)


def test_dead_owner_recovery_naturally_settles_exact_child_after_cleanup_failure(occurrence, monkeypatch):
    digest = hashlib.sha256((occurrence / "request.json").read_bytes()).hexdigest()
    worker.save(
        occurrence / "create-intent.json",
        {"name": "voices-" + occurrence.name, "invocation": occurrence.name, "request_sha256": digest},
    )
    worker.save(occurrence / "container.json", {"id": "owned-cid", "request_sha256": digest})
    worker.save(occurrence / "owner.json", {"pid": 123, "boot": "old", "ticks": "old"})
    (occurrence / "result.json").write_text("{}")
    container = {
        "Id": "owned-cid",
        "Config": {"Labels": {"voices.invocation": occurrence.name, "voices.request": digest}},
        "State": {"Running": True, "ExitCode": 0},
    }
    present = True
    fail_removal = True
    calls = []

    def inspect(target):
        assert target == "owned-cid"
        return container if present else None

    def docker(*args):
        nonlocal present
        calls.append(args)
        if args == ("wait", "owned-cid"):
            container["State"]["Running"] = False
        elif args == ("rm", "owned-cid"):
            if fail_removal:
                raise OSError("synthetic cleanup transport loss")
            present = False
        else:
            pytest.fail("Recovery must not create/start a child")
        return CompletedProcess(args, 0, b"0", b"")

    monkeypatch.setattr(worker, "inspect", inspect)
    monkeypatch.setattr(worker, "docker", docker)
    with pytest.raises(OSError, match="cleanup transport loss"):
        worker.settle(occurrence)
    assert not (occurrence / "terminal.json").exists()
    assert worker.state(occurrence)["state"] == "unknown"
    assert (occurrence / "child-exit.json").is_file()
    fail_removal = False
    worker.settle(occurrence)
    terminal = worker.state(occurrence)
    assert terminal["state"] == "completed" and terminal["owned_container_absent"]
    assert calls == [("wait", "owned-cid"), ("rm", "owned-cid"), ("rm", "owned-cid")]


@pytest.mark.parametrize("existing_pointer", [False, True])
def test_current_replace_interruption_keeps_exact_legacy_reconciliation_recoverable(
    occurrence, monkeypatch, existing_pointer
):
    worker.publish_terminal(occurrence, 1, 0)
    if existing_pointer:
        worker.current_write(occurrence.parent, {"schema": 1, "invocation": occurrence.name, "state": "running"})
    replace = worker.os.replace

    def interrupted(*_args):
        raise OSError("synthetic pre-replace interruption")

    monkeypatch.setattr(worker.os, "replace", interrupted)
    with pytest.raises(OSError, match="pre-replace"):
        if existing_pointer:
            worker.settle(occurrence)
        else:
            worker.reconcile_custody(occurrence.parent, [occurrence.name])
    assert list(occurrence.glob("current.json.*.partial"))
    assert {p.name for p in occurrence.parent.iterdir()} == {occurrence.name, "admission.lock"} | (
        {"current.json"} if existing_pointer else set()
    )
    monkeypatch.setattr(worker.os, "replace", replace)
    monkeypatch.setattr(worker, "docker", lambda *_: pytest.fail("must not replay inference"))
    if existing_pointer:
        worker.settle(occurrence)
    else:
        worker.reconcile_custody(occurrence.parent, [occurrence.name])
    worker.baseline_clearance(occurrence.parent)


def test_mid_terminal_write_recovers_same_removed_child_without_replay(occurrence, monkeypatch):
    digest = hashlib.sha256((occurrence / "request.json").read_bytes()).hexdigest()
    worker.current_write(occurrence.parent, {"schema": 1, "invocation": occurrence.name, "state": "running"})
    worker.save(
        occurrence / "create-intent.json",
        {"name": "voices-" + occurrence.name, "invocation": occurrence.name, "request_sha256": digest},
    )
    worker.save(occurrence / "container.json", {"id": "removed-child", "request_sha256": digest})
    worker.save(occurrence / "child-exit.json", {"id": "removed-child", "request_sha256": digest, "exit_code": 0})
    (occurrence / "result.json").write_text("{}")
    monkeypatch.setattr(worker, "inspect", lambda _: None)
    monkeypatch.setattr(worker, "docker", lambda *_: pytest.fail("must not create/start/replay a removed child"))
    dump = worker.json.dump

    def interrupted(_value, stream, **_kwargs):
        stream.write('{"state":')
        stream.flush()
        raise OSError("synthetic mid-write interruption")

    monkeypatch.setattr(worker.json, "dump", interrupted)
    with pytest.raises(OSError, match="mid-write"):
        worker.settle(occurrence)
    assert not (occurrence / "terminal.json").exists()
    assert list(occurrence.glob("terminal.json.*.partial"))[0].read_text() == '{"state":'
    assert worker.state(occurrence)["state"] == "unknown"
    with pytest.raises(FileNotFoundError):
        worker.baseline_clearance(occurrence.parent)
    monkeypatch.setattr(worker.json, "dump", dump)
    worker.settle(occurrence)
    assert worker.state(occurrence)["state"] == "completed"
    committed = (occurrence / "terminal.json").read_bytes()
    with pytest.raises(FileExistsError):
        worker.publish_terminal(occurrence, 1, 0)
    assert (occurrence / "terminal.json").read_bytes() == committed
    worker.baseline_clearance(occurrence.parent)
