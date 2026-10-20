"""Audio capture and conversion helpers backed by the local ffmpeg executable."""

import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from voices.config import FALLBACK_SAMPLE_RATE
from voices.domain.errors import AudioConversionError, MissingDependencyError, RecordingError

DEFAULT_MICROPHONE_INPUT = "none:default"


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise MissingDependencyError("ffmpeg is required for audio conversion. Install it and retry.")


def _extract_ffmpeg_error(stderr: bytes | str | None, *, label: str) -> str:
    if isinstance(stderr, bytes):
        detail = stderr.decode(errors="replace").strip()
    elif isinstance(stderr, str):
        detail = stderr.strip()
    else:
        detail = ""
    final_line = detail.splitlines()[-1] if detail else "unknown ffmpeg failure"
    return f"ffmpeg failed on {label}: {final_line}"


def convert_to_reference_audio(
    source: Path,
    sample_rate: int = FALLBACK_SAMPLE_RATE,
) -> np.ndarray:
    """Convert an audio file into mono float32 PCM at the requested sample rate."""
    _require_ffmpeg()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(source),
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(sample_rate),
                "-ac",
                "1",
                "pipe:1",
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AudioConversionError(_extract_ffmpeg_error(exc.stderr, label=source.name)) from exc
    pcm = np.frombuffer(result.stdout, dtype=np.int16)
    if pcm.size == 0:
        raise AudioConversionError(f"ffmpeg returned no decodable audio for {source.name}.")
    return pcm.astype(np.float32) / 32767.0


def record_guided_audio(
    destination: Path,
    duration_seconds: float,
    sample_rate: int = FALLBACK_SAMPLE_RATE,
) -> None:
    """Capture one timed microphone clip into a WAV file."""
    _require_ffmpeg()
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                DEFAULT_MICROPHONE_INPUT,
                "-t",
                f"{duration_seconds:.1f}",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                "-y",
                str(destination),
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RecordingError(_extract_ffmpeg_error(exc.stderr, label="default microphone")) from exc


@contextmanager
def free_recording(
    destination: Path,
    sample_rate: int = FALLBACK_SAMPLE_RATE,
) -> Iterator[None]:
    """Own one microphone process until it has stopped and been collected."""
    _require_ffmpeg()
    try:
        process = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                DEFAULT_MICROPHONE_INPUT,
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                "-y",
                str(destination),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise RecordingError(f"Unable to start microphone capture: {exc}") from exc
    primary_error: BaseException | None = None
    try:
        yield
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            _finish_free_recording(process)
        except BaseException as cleanup_error:
            if primary_error is None:
                raise
            detail = str(cleanup_error) or type(cleanup_error).__name__
            primary_error.add_note(f"Microphone capture cleanup failed: {detail}")
            for note in getattr(cleanup_error, "__notes__", ()):
                primary_error.add_note(note)


def _kill_and_reap(process: subprocess.Popen[str]) -> None:
    """Collect a failed capture even if an interrupt arrives during retirement."""
    try:
        while True:
            try:
                process.kill()
                break
            except KeyboardInterrupt:
                continue
        try:
            process.communicate()
        except KeyboardInterrupt:
            pass
    finally:
        try:
            while True:
                try:
                    process.wait()
                    break
                except KeyboardInterrupt:
                    continue
        finally:
            for stream in (process.stdin, process.stderr):
                if stream is not None:
                    stream.close()


def _finish_free_recording(process: subprocess.Popen[str]) -> None:
    """Request a cooperative stop, otherwise force retirement and reject the take."""
    try:
        _stdout, stderr = process.communicate(input="q\n", timeout=15)
    except BaseException as error:
        failure: BaseException = error
        if isinstance(error, Exception):
            failure = RecordingError(f"Microphone capture did not stop cleanly: {error}")
        try:
            _kill_and_reap(process)
        except BaseException as cleanup_error:
            failure.add_note(f"Forced microphone cleanup failed: {cleanup_error!r}")
        if failure is error:
            raise
        raise failure from error
    if process.returncode != 0:
        raise RecordingError(_extract_ffmpeg_error(stderr, label="default microphone"))
