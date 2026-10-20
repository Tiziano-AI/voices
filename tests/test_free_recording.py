"""Free capture owns and retires its process without touching audio devices."""

import io
import os
import subprocess
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from voices.adapter.ffmpeg_audio import free_recording
from voices.domain.errors import MissingDependencyError, RecordingError


@pytest.fixture
def capture_process():
    process = MagicMock(spec=subprocess.Popen)
    process.communicate.return_value = ("", "")
    process.returncode = 0
    process.stdin = io.StringIO()
    process.stderr = io.StringIO()
    with (
        patch("voices.adapter.ffmpeg_audio.shutil.which", return_value="/test/ffmpeg"),
        patch("voices.adapter.ffmpeg_audio.subprocess.Popen", return_value=process) as start,
    ):
        yield process, start


def test_free_recording_requests_cooperative_stop(capture_process, tmp_path):
    process, start = capture_process

    with free_recording(tmp_path / "take.wav", sample_rate=16000) as capture:
        assert capture is None
        process.communicate.assert_not_called()

    process.communicate.assert_called_once_with(input="q\n", timeout=15)
    process.kill.assert_not_called()
    arguments = start.call_args.args[0]
    assert arguments[0] == "ffmpeg"
    assert arguments[arguments.index("-ar") + 1] == "16000"
    assert arguments[-1] == str(tmp_path / "take.wav")
    assert start.call_args.kwargs == {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
        "text": True,
    }


def test_free_recording_missing_ffmpeg_does_not_start(tmp_path):
    with (
        patch("voices.adapter.ffmpeg_audio.shutil.which", return_value=None),
        patch("voices.adapter.ffmpeg_audio.subprocess.Popen") as start,
        pytest.raises(MissingDependencyError),
        free_recording(tmp_path / "take.wav"),
    ):
        pytest.fail("capture body must not run")
    start.assert_not_called()


def test_free_recording_start_failure_does_not_run_body(capture_process, tmp_path):
    process, start = capture_process
    start.side_effect = OSError("unable to spawn")

    with pytest.raises(RecordingError, match="Unable to start microphone capture: unable to spawn"):
        with free_recording(tmp_path / "take.wav"):
            pytest.fail("capture body must not run")

    process.communicate.assert_not_called()
    process.kill.assert_not_called()


@pytest.mark.parametrize("error", [EOFError(), RuntimeError("input failed"), KeyboardInterrupt(), SystemExit(7)])
def test_free_recording_stops_on_every_body_exit(capture_process, tmp_path, error):
    process, _start = capture_process

    with pytest.raises(type(error)) as raised:
        with free_recording(tmp_path / "take.wav"):
            raise error

    assert raised.value is error
    process.communicate.assert_called_once_with(input="q\n", timeout=15)
    process.kill.assert_not_called()


def test_free_recording_rejects_unsuccessful_child(capture_process, tmp_path):
    process, _start = capture_process
    process.communicate.return_value = ("", "Device busy")
    process.returncode = 1

    with pytest.raises(RecordingError, match="Device busy"):
        with free_recording(tmp_path / "take.wav"):
            pass

    process.kill.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [subprocess.TimeoutExpired("ffmpeg", 15), RuntimeError("communicate failed"), KeyboardInterrupt()],
)
def test_free_recording_forces_and_reaps_after_stop_error(capture_process, tmp_path, error):
    process, _start = capture_process
    process.communicate.side_effect = [error, ("", "")]
    expected = KeyboardInterrupt if isinstance(error, KeyboardInterrupt) else RecordingError

    with pytest.raises(expected) as raised:
        with free_recording(tmp_path / "take.wav"):
            pass

    if expected is KeyboardInterrupt:
        assert raised.value is error
    else:
        assert raised.value.__cause__ is error
    assert process.communicate.call_args_list == [call(input="q\n", timeout=15), call()]
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with()
    assert process.stdin.closed
    assert process.stderr.closed


def test_free_recording_keeps_primary_error_and_reports_stop_failure(capture_process, tmp_path):
    process, _start = capture_process
    process.communicate.side_effect = [subprocess.TimeoutExpired("ffmpeg", 15), ("", "")]
    primary = EOFError("input ended")

    with pytest.raises(EOFError) as raised:
        with free_recording(tmp_path / "take.wav"):
            raise primary

    assert raised.value is primary
    assert any("Microphone capture cleanup failed:" in note for note in primary.__notes__)
    assert any("did not stop cleanly" in note for note in primary.__notes__)
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with()


def test_free_recording_reaps_even_if_forced_communicate_also_fails(capture_process, tmp_path):
    process, _start = capture_process
    process.communicate.side_effect = [RuntimeError("first failure"), OSError("pipe failed")]
    primary = RuntimeError("input failed")

    with pytest.raises(RuntimeError) as raised:
        with free_recording(tmp_path / "take.wav"):
            raise primary

    assert raised.value is primary
    assert any("pipe failed" in note for note in primary.__notes__)
    process.wait.assert_called_once_with()
    assert process.stdin.closed
    assert process.stderr.closed


def test_free_recording_finishes_retirement_despite_further_interrupts(capture_process, tmp_path):
    process, _start = capture_process
    process.communicate.side_effect = [KeyboardInterrupt(), KeyboardInterrupt()]
    process.kill.side_effect = [KeyboardInterrupt(), None]
    process.wait.side_effect = [KeyboardInterrupt(), 0]

    with pytest.raises(KeyboardInterrupt):
        with free_recording(tmp_path / "take.wav"):
            pass

    assert process.kill.call_count == 2
    assert process.wait.call_count == 2
    assert process.stdin.closed
    assert process.stderr.closed


@pytest.mark.parametrize("body_error", [None, EOFError(), RuntimeError("input failed"), KeyboardInterrupt()])
def test_real_child_is_reaped_and_pipes_closed_after_capture(tmp_path, body_error):
    real_popen = subprocess.Popen
    children = []

    def start_child(_arguments, **options):
        child = real_popen(
            [sys.executable, "-c", "import sys; assert sys.stdin.readline() == 'q\\n'"],
            **options,
        )
        children.append(child)
        return child

    with (
        patch("voices.adapter.ffmpeg_audio.shutil.which", return_value="/test/ffmpeg"),
        patch("voices.adapter.ffmpeg_audio.subprocess.Popen", side_effect=start_child),
    ):
        if body_error is None:
            with free_recording(tmp_path / "unused.wav"):
                pass
        else:
            with pytest.raises(type(body_error)) as raised:
                with free_recording(tmp_path / "unused.wav"):
                    raise body_error
            assert raised.value is body_error

    child = children[0]
    assert child.returncode == 0
    assert child.stdin.closed
    assert child.stderr.closed
    with pytest.raises(ChildProcessError):
        os.waitpid(child.pid, os.WNOHANG)


@pytest.mark.parametrize("interrupt", [True, False])
def test_real_child_is_killed_and_reaped_after_failed_stop(tmp_path, interrupt):
    real_popen = subprocess.Popen
    children = []

    def start_child(_arguments, **options):
        child = real_popen([sys.executable, "-c", "import threading; threading.Event().wait()"], **options)
        children.append(child)
        real_communicate = child.communicate
        calls = 0

        def interrupted_communicate(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                if interrupt:
                    raise KeyboardInterrupt
                kwargs["timeout"] = 0
            return real_communicate(*args, **kwargs)

        child.communicate = interrupted_communicate
        return child

    with (
        patch("voices.adapter.ffmpeg_audio.shutil.which", return_value="/test/ffmpeg"),
        patch("voices.adapter.ffmpeg_audio.subprocess.Popen", side_effect=start_child),
        pytest.raises(KeyboardInterrupt if interrupt else RecordingError),
        free_recording(tmp_path / "unused.wav"),
    ):
        pass

    child = children[0]
    assert child.returncode < 0
    assert child.stdin.closed
    assert child.stderr.closed
    with pytest.raises(ChildProcessError):
        os.waitpid(child.pid, os.WNOHANG)
