"""Tests for vtext_client.cli."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from vtext_client.cli import cli
from vtext_client.errors import QueueFullError, ServerConnectionError, VtextClientError
from vtext_common.types import Segment, TranscriptionResult


def make_result(text="Hello world", language="en", segments=None):
    return TranscriptionResult(
        text=text,
        language=language,
        source="audio.wav",
        duration=1.0,
        segments=segments or [Segment(0.0, 1.0, text)],
    )


@pytest.fixture
def runner():
    return CliRunner()


class TestCheckServer:
    def test_healthy_server(self, runner):
        health = {
            "status": "ok",
            "model": {"loaded": "base"},
            "queue": {"size": 0, "max": 10},
            "workers": {"busy": 0, "total": 2},
        }
        with patch("vtext_client.cli.check_health", return_value=health):
            result = runner.invoke(cli, ["--check-server"])
        assert result.exit_code == 0
        assert "ok" in result.output

    def test_unreachable_server(self, runner):
        with patch("vtext_client.cli.check_health", side_effect=ServerConnectionError("no conn")):
            result = runner.invoke(cli, ["--check-server"])
        assert result.exit_code == 1


class TestMissingInput:
    def test_no_input_shows_usage_error(self, runner):
        result = runner.invoke(cli, [])
        assert result.exit_code != 0

    def test_nonexistent_file(self, runner):
        result = runner.invoke(cli, ["/nonexistent/file.mp4"])
        assert result.exit_code == 1


class TestTranscribeFile:
    def _patch_all(self, wav_path, result):
        """Return context managers that mock the full pipeline."""
        return [
            patch("vtext_client.cli.extract_wav", return_value=wav_path),
            patch("vtext_client.cli.maybe_compress", return_value=(wav_path, None)),
            patch("vtext_client.cli.submit_job", return_value="abc12345"),
            patch("vtext_client.cli.stream_progress", return_value=result),
        ]

    def test_outputs_to_stdout_with_dash(self, runner, tmp_path):
        """Test that -o - outputs to stdout instead of a file."""
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.touch()
        result = make_result("Hello world")

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="abc12345"), \
             patch("vtext_client.cli.stream_progress", return_value=result):
            r = runner.invoke(cli, [str(input_file), "-o", "-"])

        assert r.exit_code == 0
        assert "Hello world" in r.output

    def test_default_outputs_to_text_subdir(self, runner, tmp_path):
        """Test that default behavior creates text/ subdir."""
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.touch()
        result = make_result("Hello world")

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="abc12345"), \
             patch("vtext_client.cli.stream_progress", return_value=result):
            r = runner.invoke(cli, [str(input_file)])

        assert r.exit_code == 0
        text_dir = tmp_path / "text"
        assert text_dir.exists()
        out_file = text_dir / "audio.txt"
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "Hello world"

    def test_writes_to_output_file(self, runner, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.touch()
        out_file = tmp_path / "out.txt"
        result = make_result("Transcribed text")

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="abc12345"), \
             patch("vtext_client.cli.stream_progress", return_value=result):
            r = runner.invoke(cli, [str(input_file), "-o", str(out_file)])

        assert r.exit_code == 0
        assert out_file.read_text(encoding="utf-8") == "Transcribed text"

    def test_queue_full_exits_with_1(self, runner, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.touch()

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job",
                   side_effect=QueueFullError("Queue full", queue_size=10, estimated_wait=300)):
            r = runner.invoke(cli, [str(input_file)])

        assert r.exit_code == 1

    def test_server_connection_error_exits_with_1(self, runner, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        with patch("vtext_client.cli.extract_wav",
                   side_effect=ServerConnectionError("Cannot connect")):
            r = runner.invoke(cli, [str(input_file)])
        assert r.exit_code == 1

    def test_wav_temp_file_cleaned_up(self, runner, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")
        result = make_result()

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="job1"), \
             patch("vtext_client.cli.stream_progress", return_value=result):
            runner.invoke(cli, [str(input_file)])

        assert not wav.exists()

    def test_compressed_file_cleaned_up(self, runner, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"wav")
        zst = tmp_path / "audio.wav.zst"
        zst.write_bytes(b"compressed")
        result = make_result()

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(zst, "zstd")), \
             patch("vtext_client.cli.submit_job", return_value="job1"), \
             patch("vtext_client.cli.stream_progress", return_value=result):
            runner.invoke(cli, [str(input_file)])

        assert not wav.exists()
        assert not zst.exists()

    def test_format_option_passed_to_submit(self, runner, tmp_path):
        input_file = tmp_path / "audio.mp3"
        input_file.touch()
        wav = tmp_path / "audio.wav"
        wav.touch()
        result = make_result()
        submitted_fmt = []

        def fake_submit(server, path, encoding=None, language=None, fmt="txt", model=None, timeout=30):
            submitted_fmt.append(fmt)
            return "job1"

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", side_effect=fake_submit), \
             patch("vtext_client.cli.stream_progress", return_value=result):
            runner.invoke(cli, [str(input_file), "-f", "srt"])

        assert submitted_fmt[0] == "srt"


class TestBatchMode:
    def test_directory_triggers_batch(self, runner, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "clip.mp4").touch()

        with patch("vtext_client.cli.batch_transcribe") as mock_batch:
            r = runner.invoke(cli, [str(media_dir)])

        mock_batch.assert_called_once()
        assert r.exit_code == 0
