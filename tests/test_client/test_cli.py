"""Tests for vtext_client.cli."""
import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from vtext_client.cli import cli
from vtext_client.errors import (
    QueueFullError,
    RefineError,
    ServerConnectionError,
    VtextClientError,
)
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


@pytest.fixture(autouse=True)
def stub_default_refine():
    """Keep CLI tests independent from local config and production LLM services."""
    with patch(
        "vtext_client.cli.refine_text",
        return_value=("Clean text", "# Summary"),
    ):
        yield


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

    def test_default_output_next_to_source(self, runner, tmp_path):
        """Default raw output is <stem>_raw.<fmt> next to the source file."""
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
        out_file = tmp_path / "audio_raw.txt"
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "Hello world"
        # raw output no longer goes to a text/ subdir by default
        assert not (tmp_path / "text").exists()

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

    def test_vbook_bundle_writes_stable_outputs_and_manifest(self, runner, tmp_path):
        course_dir = tmp_path / "course"
        series_dir = course_dir / "series"
        series_dir.mkdir(parents=True)
        input_file = series_dir / "lesson.mp4"
        input_file.touch()
        out_dir = tmp_path / "out"
        wav = tmp_path / "lesson.wav"
        wav.touch()
        result = make_result("Hello world")

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="abc12345"), \
             patch("vtext_client.cli.stream_progress", return_value=result), \
             patch(
                 "vtext_client.cli.refine_text",
                 return_value=("Clean text", "# Summary"),
             ) as mock_refine:
            r = runner.invoke(
                cli,
                [
                    str(input_file),
                    "--bundle",
                    "vbook",
                    "-o",
                    str(out_dir),
                    "-f",
                    "srt",
                    "-l",
                    "zh",
                ],
            )

        assert r.exit_code == 0
        assert (out_dir / "transcript.raw.txt").read_text(encoding="utf-8") == "Hello world"
        assert "00:00:00,000" in (out_dir / "transcript.raw.srt").read_text(encoding="utf-8")
        assert (out_dir / "transcript.clean.txt").read_text(encoding="utf-8") == "Clean text"
        assert (out_dir / "summary.md").read_text(encoding="utf-8") == "# Summary"
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "done"
        assert manifest["course"] == "course"
        assert manifest["series"] == "series"
        assert manifest["lesson_title"] == "lesson"
        assert manifest["language"] == "zh"
        assert manifest["outputs"] == {
            "raw_txt": "transcript.raw.txt",
            "raw_srt": "transcript.raw.srt",
            "clean_txt": "transcript.clean.txt",
            "summary_md": "summary.md",
        }
        assert manifest["errors"] == []
        assert mock_refine.call_args.kwargs["mode"] == "server"

    def test_vbook_bundle_rejects_direct_refine(self, runner, tmp_path):
        input_file = tmp_path / "lesson.mp4"
        input_file.touch()

        r = runner.invoke(
            cli,
            [
                str(input_file),
                "--bundle",
                "vbook",
                "--output",
                str(tmp_path / "out"),
                "--refine-mode",
                "direct",
            ],
        )

        assert r.exit_code == 2
        assert "requires server-side refine" in r.output

    def test_vbook_bundle_rejects_disabled_refine(self, runner, tmp_path):
        input_file = tmp_path / "lesson.mp4"
        input_file.touch()

        r = runner.invoke(
            cli,
            [
                str(input_file),
                "--bundle",
                "vbook",
                "--output",
                str(tmp_path / "out"),
                "--no-refine",
            ],
        )

        assert r.exit_code == 2
        assert "requires refine to be enabled" in r.output

    def test_vbook_bundle_writes_fallback_outputs_when_refine_fails(self, runner, tmp_path):
        course_dir = tmp_path / "course"
        series_dir = course_dir / "series"
        series_dir.mkdir(parents=True)
        input_file = series_dir / "lesson.mp4"
        input_file.touch()
        out_dir = tmp_path / "out"
        wav = tmp_path / "lesson.wav"
        wav.touch()
        result = make_result("Raw ASR text")

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="abc12345"), \
             patch("vtext_client.cli.stream_progress", return_value=result), \
             patch("vtext_client.cli.refine_text", side_effect=RefineError("llm timeout")):
            r = runner.invoke(
                cli,
                [
                    str(input_file),
                    "--bundle",
                    "vbook",
                    "-o",
                    str(out_dir),
                    "-f",
                    "srt",
                    "-l",
                    "zh",
                ],
            )

        assert r.exit_code == 0
        assert (out_dir / "transcript.clean.txt").read_text(encoding="utf-8") == "Raw ASR text"
        summary = (out_dir / "summary.md").read_text(encoding="utf-8")
        assert "vtext refine was unavailable" in summary
        assert "Raw ASR text" in summary
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "done"
        assert manifest["outputs"]["clean_txt"] == "transcript.clean.txt"
        assert manifest["outputs"]["summary_md"] == "summary.md"
        assert manifest["errors"][0]["stage"] == "refine"
        assert manifest["errors"][0]["code"] == "refine_error"

    def test_vbook_bundle_uses_chunked_refine_for_long_transcript(self, runner, tmp_path):
        input_file = tmp_path / "lesson.mp4"
        input_file.touch()
        out_dir = tmp_path / "out"
        wav = tmp_path / "lesson.wav"
        wav.touch()
        result = make_result("x" * 6001)

        with patch("vtext_client.cli.extract_wav", return_value=wav), \
             patch("vtext_client.cli.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.cli.submit_job", return_value="abc12345"), \
             patch("vtext_client.cli.stream_progress", return_value=result), \
             patch("vtext_client.cli.refine_text") as regular_refine, \
             patch(
                 "vtext_client.cli.refine_text_chunked",
                 return_value=("Chunked clean", "# Chunked summary"),
             ) as chunked_refine:
            r = runner.invoke(
                cli,
                [
                    str(input_file),
                    "--bundle",
                    "vbook",
                    "--output",
                    str(out_dir),
                ],
            )

        assert r.exit_code == 0
        regular_refine.assert_not_called()
        chunked_refine.assert_called_once()
        assert chunked_refine.call_args.kwargs["mode"] == "server"

    def test_vbook_refine_only_recovers_existing_bundle(self, runner, tmp_path):
        out_dir = tmp_path / "artifact"
        out_dir.mkdir()
        raw_path = out_dir / "transcript.raw.txt"
        raw_path.write_text("x" * 6001, encoding="utf-8")
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "outputs": {"raw_txt": "transcript.raw.txt"},
                    "models": {"asr": "small", "refine": "qwen3.5:9b"},
                    "errors": [
                        {
                            "stage": "refine",
                            "code": "refine_error",
                            "message": "timeout",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch(
            "vtext_client.cli._run_vbook_refine",
            return_value=("Recovered clean", "# Recovered summary"),
        ):
            r = runner.invoke(
                cli,
                [
                    str(raw_path),
                    "--refine-only",
                    "--bundle",
                    "vbook",
                    "--output",
                    str(out_dir),
                ],
            )

        assert r.exit_code == 0
        assert (out_dir / "transcript.clean.txt").read_text(
            encoding="utf-8"
        ) == "Recovered clean"
        recovered = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert recovered["errors"] == []
        assert recovered["outputs"]["summary_md"] == "summary.md"
        assert recovered["recovery"]["mode"] == "chunked_refine_only"
        assert recovered["recovery"]["previous_errors"][0]["code"] == "refine_error"

    def test_vbook_refine_only_rejects_invalid_manifest_before_refine(
        self, runner, tmp_path
    ):
        out_dir = tmp_path / "artifact"
        out_dir.mkdir()
        raw_path = out_dir / "transcript.raw.txt"
        raw_path.write_text("Raw transcript", encoding="utf-8")
        (out_dir / "manifest.json").write_text(
            json.dumps({"errors": "invalid", "outputs": {}, "models": {}}),
            encoding="utf-8",
        )

        with patch("vtext_client.cli._run_vbook_refine") as run_refine:
            r = runner.invoke(
                cli,
                [
                    str(raw_path),
                    "--refine-only",
                    "--bundle",
                    "vbook",
                    "--output",
                    str(out_dir),
                ],
            )

        assert r.exit_code != 0
        assert "errors must be an array of objects" in r.output
        run_refine.assert_not_called()

    def test_vbook_bundle_writes_failed_manifest_on_transcription_error(self, runner, tmp_path):
        input_file = tmp_path / "course" / "series" / "lesson.mp4"
        input_file.parent.mkdir(parents=True)
        input_file.touch()
        out_dir = tmp_path / "out"

        with patch("vtext_client.cli.extract_wav", side_effect=VtextClientError("boom")):
            r = runner.invoke(
                cli,
                [str(input_file), "--bundle", "vbook", "-o", str(out_dir), "-l", "zh"],
            )

        assert r.exit_code == 1
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "failed"
        assert manifest["outputs"] == {}
        assert manifest["errors"][0]["stage"] == "transcription"
        assert manifest["errors"][0]["code"] == "client_error"


class TestBatchMode:
    def test_directory_triggers_batch(self, runner, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "clip.mp4").touch()

        with patch("vtext_client.cli.batch_transcribe") as mock_batch:
            r = runner.invoke(cli, [str(media_dir)])

        mock_batch.assert_called_once()
        assert r.exit_code == 0

    def test_batch_with_output_dir(self, runner, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "clip.mp4").touch()
        output_dir = tmp_path / "output"

        with patch("vtext_client.cli.batch_transcribe") as mock_batch:
            r = runner.invoke(cli, [str(media_dir), "-o", str(output_dir)])

        assert r.exit_code == 0
        mock_batch.assert_called_once()
        assert mock_batch.call_args[1]["output_dir"] == output_dir

    def test_batch_rejects_stdout(self, runner, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "clip.mp4").touch()

        r = runner.invoke(cli, [str(media_dir), "-o", "-"])

        assert r.exit_code != 0
        assert "does not support stdout" in r.output
