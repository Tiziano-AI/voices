"""CLI capture exits are translated only after the adapter retires FFmpeg."""

import io
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from voices.cli import app
from voices.cli_review import _capture_free_take, record_and_review
from voices.domain.errors import RecordingError


@pytest.fixture
def capture_process():
    process = MagicMock(spec=subprocess.Popen)
    process.returncode = 0
    process.communicate.return_value = ("", "")
    process.stdin = io.StringIO()
    process.stderr = io.StringIO()
    with (
        patch("voices.adapter.ffmpeg_audio.shutil.which", return_value="/test/ffmpeg"),
        patch("voices.adapter.ffmpeg_audio.subprocess.Popen", return_value=process),
    ):
        yield process


@pytest.mark.parametrize("error", [EOFError(), KeyboardInterrupt(), RuntimeError("input failed")])
def test_cli_failed_input_retires_capture_without_review(capture_process, tmp_path, error):
    expected = typer.Abort if isinstance(error, (EOFError, KeyboardInterrupt)) else RuntimeError
    with (
        patch("voices.cli_review.console.input", side_effect=error),
        patch("voices.cli_review.prepare_clone_review") as review,
        pytest.raises(expected) as raised,
    ):
        record_and_review(tmp_path / "take.wav", "free", "English", None, tmp_path / "library")

    if expected is typer.Abort:
        assert raised.value.__cause__ is error
    else:
        assert raised.value is error
    capture_process.communicate.assert_called_once_with(input="q\n", timeout=15)
    capture_process.kill.assert_not_called()
    review.assert_not_called()


@pytest.mark.parametrize("error", [EOFError(), KeyboardInterrupt()])
def test_cli_reports_cleanup_failure_before_abort_translation(capture_process, tmp_path, error):
    capture_process.returncode = 1
    capture_process.communicate.return_value = ("", "Device busy")

    with (
        patch("voices.cli_review.console.input", side_effect=error),
        patch("voices.cli_review.err_console.print") as report,
        pytest.raises(typer.Abort) as raised,
    ):
        _capture_free_take(tmp_path / "take.wav")

    assert raised.value.__cause__ is error
    report.assert_called_once_with(
        "Microphone capture cleanup failed: ffmpeg failed on default microphone: Device busy",
        markup=False,
    )


def test_cli_real_error_output_keeps_cleanup_diagnostic(capture_process, tmp_path):
    capture_process.returncode = 1
    capture_process.communicate.return_value = ("", "Device busy")
    with patch("voices.cli_review.console.input", side_effect=EOFError):
        result = CliRunner().invoke(app, ["record", "--mode", "free", "--library", str(tmp_path / "library")])

    assert result.exit_code == 1
    assert "Microphone capture cleanup failed:" in result.output
    assert "Device busy" in " ".join(result.output.split())
    assert "Aborted" in result.output


def test_cli_forced_stop_never_enters_review(capture_process, tmp_path):
    capture_process.communicate.side_effect = [subprocess.TimeoutExpired("ffmpeg", 15), ("", "")]
    with (
        patch("voices.cli_review.console.input", return_value=""),
        patch("voices.cli_review.prepare_clone_review") as review,
        pytest.raises(RecordingError, match="did not stop cleanly"),
    ):
        record_and_review(tmp_path / "take.wav", "free", "English", None, tmp_path / "library")

    capture_process.kill.assert_called_once_with()
    capture_process.wait.assert_called_once_with()
    review.assert_not_called()


def test_review_failure_cannot_leave_real_capture_running_or_stop_it_twice(tmp_path):
    real_popen = subprocess.Popen
    children = []

    def start_child(_arguments, **options):
        child = real_popen([sys.executable, "-c", "import sys; sys.stdin.readline()"], **options)
        child.communicate = MagicMock(wraps=child.communicate)
        children.append(child)
        return child

    def fail_review(**_kwargs):
        child = children[0]
        assert child.returncode == 0
        assert child.stdin.closed
        assert child.stderr.closed
        child.communicate.assert_called_once_with(input="q\n", timeout=15)
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        raise RuntimeError("review failed after capture")

    with (
        patch("voices.adapter.ffmpeg_audio.shutil.which", return_value="/test/ffmpeg"),
        patch("voices.adapter.ffmpeg_audio.subprocess.Popen", side_effect=start_child),
        patch("voices.cli_review.console.input", return_value=""),
        patch("voices.cli_review.prepare_clone_review", side_effect=fail_review) as review,
        pytest.raises(RuntimeError, match="review failed after capture"),
    ):
        record_and_review(tmp_path / "take.wav", "free", "English", None, tmp_path / "library")

    assert len(children) == 1
    review.assert_called_once()
