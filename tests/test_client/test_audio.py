"""Tests for vtext_client.audio."""
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vtext_client.audio import extract_wav, maybe_compress, _check_ffmpeg, COMPRESS_THRESHOLD
from vtext_client.errors import VtextClientError


class TestCheckFfmpeg:
    def test_found(self):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            _check_ffmpeg()  # should not raise

    def test_not_found_raises(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(VtextClientError, match="ffmpeg not found"):
                _check_ffmpeg()


class TestExtractWav:
    def test_success(self, tmp_path):
        input_file = tmp_path / "video.mp4"
        input_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                # We need the output file to actually exist
                def fake_run(cmd, **kwargs):
                    # The last positional arg is the output path
                    out = Path(cmd[-1])
                    out.write_bytes(b"WAV data")
                    return mock_result

                mock_run.side_effect = fake_run
                out = extract_wav(input_file)

        assert out.exists()
        assert out.suffix == ".wav"
        out.unlink(missing_ok=True)

    def test_ffmpeg_failure_raises(self, tmp_path):
        input_file = tmp_path / "video.mp4"
        input_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffmpeg error"

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run", return_value=mock_result):
                with pytest.raises(VtextClientError, match="ffmpeg failed"):
                    extract_wav(input_file)

    def test_ffmpeg_missing_raises(self, tmp_path):
        input_file = tmp_path / "video.mp4"
        input_file.touch()
        with patch("shutil.which", return_value=None):
            with pytest.raises(VtextClientError, match="ffmpeg not found"):
                extract_wav(input_file)

    def test_ffmpeg_command_includes_16khz_mono(self, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()

        mock_result = MagicMock()
        mock_result.returncode = 0

        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            Path(cmd[-1]).write_bytes(b"data")
            return mock_result

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run", side_effect=fake_run):
                out = extract_wav(input_file)
                out.unlink(missing_ok=True)

        assert "-ar" in captured_cmd
        assert "16000" in captured_cmd
        assert "-ac" in captured_cmd
        assert "1" in captured_cmd


class TestMaybeCompress:
    def test_small_file_no_compression(self, tmp_path):
        wav = tmp_path / "small.wav"
        wav.write_bytes(b"x" * 100)  # 100 bytes, well below threshold
        path, encoding = maybe_compress(wav)
        assert path == wav
        assert encoding is None

    def test_large_file_compresses(self, tmp_path):
        wav = tmp_path / "large.wav"
        # Write a file just over the 100MB threshold
        wav.write_bytes(b"RIFF" + b"\x00" * (COMPRESS_THRESHOLD + 1))
        path, encoding = maybe_compress(wav)
        try:
            assert encoding == "zstd"
            assert path != wav
            assert path.suffix == ".zst"
            assert path.exists()
        finally:
            path.unlink(missing_ok=True)

    def test_compressed_file_is_smaller(self, tmp_path):
        wav = tmp_path / "large.wav"
        # Compressible content: repeating pattern
        wav.write_bytes(b"\x00" * (COMPRESS_THRESHOLD + 1024 * 1024))
        original_size = wav.stat().st_size
        path, encoding = maybe_compress(wav)
        try:
            assert encoding == "zstd"
            assert path.stat().st_size < original_size
        finally:
            path.unlink(missing_ok=True)
