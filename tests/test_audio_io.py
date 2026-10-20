import subprocess
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voices.adapter.ffmpeg_audio import (
    convert_to_reference_audio,
    record_guided_audio,
)
from voices.domain.errors import AudioConversionError, MissingDependencyError, RecordingError
from voices.store.library_store import write_wav


def test_write_wav_creates_valid_file(tmp_path):
    path = tmp_path / "test.wav"
    audio = np.zeros(2400, dtype=np.float32)
    write_wav(path, audio, 24000)

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24000
        assert wav_file.getnframes() == 2400


def test_write_wav_clamps_values(tmp_path):
    path = tmp_path / "test.wav"
    audio = np.array([-2.0, -1.0, 0.0, 1.0, 2.0], dtype=np.float32)
    write_wav(path, audio, 24000)

    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.readframes(5)
    pcm = np.frombuffer(frames, dtype=np.int16)
    assert pcm[0] == -32767
    assert pcm[4] == 32767
    assert pcm[2] == 0


def test_write_wav_silence(tmp_path):
    path = tmp_path / "silence.wav"
    audio = np.zeros(100, dtype=np.float32)
    write_wav(path, audio, 16000)

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getframerate() == 16000
        frames = wav_file.readframes(100)
    pcm = np.frombuffer(frames, dtype=np.int16)
    assert np.all(pcm == 0)


@patch("voices.adapter.ffmpeg_audio.shutil")
def test_convert_missing_ffmpeg_raises(mock_shutil, tmp_path):
    mock_shutil.which.return_value = None
    with pytest.raises(MissingDependencyError, match="ffmpeg is required"):
        convert_to_reference_audio(tmp_path / "input.wav")


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_convert_returns_float32_mono(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    pcm_bytes = np.zeros(100, dtype=np.int16).tobytes()
    mock_subprocess.run.return_value = MagicMock(stdout=pcm_bytes, returncode=0)
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError

    result = convert_to_reference_audio(tmp_path / "input.opus", sample_rate=24000)

    assert result.dtype == np.float32
    assert result.shape == (100,)
    assert np.all(result == 0.0)
    call_args = mock_subprocess.run.call_args[0][0]
    assert call_args[0] == "ffmpeg"
    assert "-ar" in call_args
    assert call_args[call_args.index("-ar") + 1] == "24000"
    assert "-ac" in call_args
    assert call_args[call_args.index("-ac") + 1] == "1"


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_convert_rejects_empty_decoded_audio(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    mock_subprocess.run.return_value = MagicMock(stdout=b"", returncode=0)
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError

    with pytest.raises(AudioConversionError, match="no decodable audio"):
        convert_to_reference_audio(tmp_path / "empty.wav")


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_convert_normalizes_int16_range(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    pcm = np.array([32767, -32767, 0, 16384], dtype=np.int16)
    mock_subprocess.run.return_value = MagicMock(stdout=pcm.tobytes(), returncode=0)
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError

    result = convert_to_reference_audio(tmp_path / "loud.wav")

    assert abs(result[0] - 1.0) < 1e-4
    assert abs(result[1] + 1.0) < 1e-4
    assert result[2] == 0.0
    assert 0.49 < result[3] < 0.51


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_convert_ffmpeg_failure_raises(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError
    mock_subprocess.run.side_effect = subprocess.CalledProcessError(
        1,
        "ffmpeg",
        stderr=b"No such file or directory\nCorrupt header detected",
    )

    with pytest.raises(AudioConversionError, match="Corrupt header detected"):
        convert_to_reference_audio(tmp_path / "broken.aac")


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_convert_custom_sample_rate(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    pcm_bytes = np.zeros(10, dtype=np.int16).tobytes()
    mock_subprocess.run.return_value = MagicMock(stdout=pcm_bytes, returncode=0)
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError

    convert_to_reference_audio(tmp_path / "input.mp3", sample_rate=16000)

    call_args = mock_subprocess.run.call_args[0][0]
    assert call_args[call_args.index("-ar") + 1] == "16000"


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_record_guided_audio_calls_ffmpeg(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    mock_subprocess.run.return_value = MagicMock(returncode=0)
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError

    record_guided_audio(tmp_path / "take.wav", duration_seconds=14.0)

    call_args = mock_subprocess.run.call_args[0][0]
    assert call_args[0] == "ffmpeg"
    assert "-t" in call_args
    assert call_args[call_args.index("-t") + 1] == "14.0"
    assert call_args[-1].endswith("take.wav")


@patch("voices.adapter.ffmpeg_audio.shutil")
@patch("voices.adapter.ffmpeg_audio.subprocess")
def test_record_guided_audio_raises_on_failure(mock_subprocess, mock_shutil, tmp_path):
    mock_shutil.which.return_value = "/usr/local/bin/ffmpeg"
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError
    mock_subprocess.run.side_effect = subprocess.CalledProcessError(
        1,
        "ffmpeg",
        stderr=b"Permission denied",
    )

    with pytest.raises(RecordingError, match="Permission denied"):
        record_guided_audio(tmp_path / "take.wav", duration_seconds=14.0)
