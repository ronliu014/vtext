"""Tests for vtext_client.batch."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vtext_client.batch import batch_transcribe, _process_one, SUPPORTED_EXTENSIONS
from vtext_client.errors import VtextClientError
from vtext_common.types import Segment, TranscriptionResult


def make_result(text="Hello"):
    return TranscriptionResult(
        text=text,
        language="en",
        source="audio.wav",
        duration=1.0,
        segments=[Segment(0.0, 1.0, text)],
    )


class TestSupportedExtensions:
    def test_includes_common_video(self):
        assert ".mp4" in SUPPORTED_EXTENSIONS
        assert ".mkv" in SUPPORTED_EXTENSIONS
        assert ".mov" in SUPPORTED_EXTENSIONS

    def test_includes_common_audio(self):
        assert ".mp3" in SUPPORTED_EXTENSIONS
        assert ".wav" in SUPPORTED_EXTENSIONS
        assert ".m4a" in SUPPORTED_EXTENSIONS


class TestProcessOne:
    def test_success_writes_output(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav data")
        result = make_result("Transcribed")

        with patch("vtext_client.batch.extract_wav", return_value=wav), \
             patch("vtext_client.batch.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.batch.submit_job", return_value="job1"), \
             patch("vtext_client.batch.stream_progress", return_value=result):
            out_path = _process_one(input_file, server="http://localhost:8000",
                                    fmt="txt", language=None, model=None)

        assert out_path == input_file.with_suffix(".txt")
        assert out_path.read_text() == "Transcribed"

    def test_cleans_up_wav(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result()

        with patch("vtext_client.batch.extract_wav", return_value=wav), \
             patch("vtext_client.batch.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.batch.submit_job", return_value="job1"), \
             patch("vtext_client.batch.stream_progress", return_value=result):
            _process_one(input_file, server="http://localhost:8000",
                         fmt="txt", language=None, model=None)

        assert not wav.exists()

    def test_cleans_up_compressed_file(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        zst = tmp_path / "clip.wav.zst"
        zst.write_bytes(b"compressed")
        result = make_result()

        with patch("vtext_client.batch.extract_wav", return_value=wav), \
             patch("vtext_client.batch.maybe_compress", return_value=(zst, "zstd")), \
             patch("vtext_client.batch.submit_job", return_value="job1"), \
             patch("vtext_client.batch.stream_progress", return_value=result):
            _process_one(input_file, server="http://localhost:8000",
                         fmt="txt", language=None, model=None)

        assert not wav.exists()
        assert not zst.exists()

    def test_uses_formatted_result_when_available(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result("raw text")
        result.formatted = "1\n00:00:00,000 --> 00:00:01,000\nraw text\n"

        with patch("vtext_client.batch.extract_wav", return_value=wav), \
             patch("vtext_client.batch.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.batch.submit_job", return_value="job1"), \
             patch("vtext_client.batch.stream_progress", return_value=result):
            out_path = _process_one(input_file, server="http://localhost:8000",
                                    fmt="srt", language=None, model=None)

        assert "00:00:00,000" in out_path.read_text()

    def test_srt_output_extension(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result()

        with patch("vtext_client.batch.extract_wav", return_value=wav), \
             patch("vtext_client.batch.maybe_compress", return_value=(wav, None)), \
             patch("vtext_client.batch.submit_job", return_value="job1"), \
             patch("vtext_client.batch.stream_progress", return_value=result):
            out_path = _process_one(input_file, server="http://localhost:8000",
                                    fmt="srt", language=None, model=None)

        assert out_path.suffix == ".srt"


class TestBatchTranscribe:
    def test_empty_directory(self, tmp_path, capsys):
        from click.testing import CliRunner
        # batch_transcribe uses click.echo, which writes to stderr
        batch_transcribe(tmp_path, server="http://localhost:8000",
                         fmt="txt", language=None, model=None, jobs=1)
        # Should not raise; just prints a message

    def test_finds_media_files(self, tmp_path):
        (tmp_path / "clip1.mp4").touch()
        (tmp_path / "clip2.mp3").touch()
        (tmp_path / "notes.txt").touch()  # should be ignored
        result = make_result()

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path)
            # Return a fake output path
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(tmp_path, server="http://localhost:8000",
                             fmt="txt", language=None, model=None, jobs=1)

        names = {p.name for p in processed}
        assert "clip1.mp4" in names
        assert "clip2.mp3" in names
        assert "notes.txt" not in names

    def test_ignores_non_media_files(self, tmp_path):
        (tmp_path / "readme.md").touch()
        (tmp_path / "data.json").touch()
        result = make_result()

        processed = []
        with patch("vtext_client.batch._process_one", side_effect=lambda p, **kw: processed.append(p)):
            batch_transcribe(tmp_path, server="http://localhost:8000",
                             fmt="txt", language=None, model=None, jobs=1)

        assert processed == []

    def test_parallel_jobs(self, tmp_path):
        for i in range(4):
            (tmp_path / f"clip{i}.mp4").touch()

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path.name)
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(tmp_path, server="http://localhost:8000",
                             fmt="txt", language=None, model=None, jobs=2)

        assert len(processed) == 4

    def test_failed_file_does_not_abort_others(self, tmp_path):
        (tmp_path / "good.mp4").touch()
        (tmp_path / "bad.mp4").touch()

        def fake_process(path, **kwargs):
            if path.name == "bad.mp4":
                raise VtextClientError("extraction failed")
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            # Should not raise even when one file fails
            batch_transcribe(tmp_path, server="http://localhost:8000",
                             fmt="txt", language=None, model=None, jobs=1)

    def test_recurses_into_subdirectories(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.mp4").touch()

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path)
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(tmp_path, server="http://localhost:8000",
                             fmt="txt", language=None, model=None, jobs=1)

        assert any(p.name == "nested.mp4" for p in processed)
