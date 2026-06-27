"""Tests for vtext_client.batch."""

from unittest.mock import patch


from vtext_client.batch import batch_transcribe, _process_one, SUPPORTED_EXTENSIONS
from vtext_client._batchprogress import BatchProgress
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
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav data")
        result = make_result("Transcribed")

        with (
            patch("vtext_client.batch.extract_wav", return_value=wav),
            patch("vtext_client.batch.maybe_compress", return_value=(wav, None)),
            patch("vtext_client.batch.submit_job", return_value="job1"),
            patch("vtext_client.batch.stream_progress", return_value=result),
        ):
            out_path = _process_one(
                input_file,
                base_dir=tmp_path,
                text_dir=text_dir,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
            )

        assert out_path == text_dir / "clip_raw.txt"
        assert out_path.read_text(encoding="utf-8") == "Transcribed"

    def test_cleans_up_wav(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result()

        with (
            patch("vtext_client.batch.extract_wav", return_value=wav),
            patch("vtext_client.batch.maybe_compress", return_value=(wav, None)),
            patch("vtext_client.batch.submit_job", return_value="job1"),
            patch("vtext_client.batch.stream_progress", return_value=result),
        ):
            _process_one(
                input_file,
                base_dir=tmp_path,
                text_dir=text_dir,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
            )

        assert not wav.exists()

    def test_cleans_up_compressed_file(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        zst = tmp_path / "clip.wav.zst"
        zst.write_bytes(b"compressed")
        result = make_result()

        with (
            patch("vtext_client.batch.extract_wav", return_value=wav),
            patch("vtext_client.batch.maybe_compress", return_value=(zst, "zstd")),
            patch("vtext_client.batch.submit_job", return_value="job1"),
            patch("vtext_client.batch.stream_progress", return_value=result),
        ):
            _process_one(
                input_file,
                base_dir=tmp_path,
                text_dir=text_dir,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
            )

        assert not wav.exists()
        assert not zst.exists()

    def test_uses_formatted_result_when_available(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result("raw text")
        result.formatted = "1\n00:00:00,000 --> 00:00:01,000\nraw text\n"

        with (
            patch("vtext_client.batch.extract_wav", return_value=wav),
            patch("vtext_client.batch.maybe_compress", return_value=(wav, None)),
            patch("vtext_client.batch.submit_job", return_value="job1"),
            patch("vtext_client.batch.stream_progress", return_value=result),
        ):
            out_path = _process_one(
                input_file,
                base_dir=tmp_path,
                text_dir=text_dir,
                server="http://localhost:8000",
                fmt="srt",
                language=None,
                model=None,
            )

        assert "00:00:00,000" in out_path.read_text(encoding="utf-8")

    def test_srt_output_extension(self, tmp_path):
        input_file = tmp_path / "clip.mp4"
        input_file.touch()
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result()

        with (
            patch("vtext_client.batch.extract_wav", return_value=wav),
            patch("vtext_client.batch.maybe_compress", return_value=(wav, None)),
            patch("vtext_client.batch.submit_job", return_value="job1"),
            patch("vtext_client.batch.stream_progress", return_value=result),
        ):
            out_path = _process_one(
                input_file,
                base_dir=tmp_path,
                text_dir=text_dir,
                server="http://localhost:8000",
                fmt="srt",
                language=None,
                model=None,
            )

        assert out_path.suffix == ".srt"

    def test_output_preserves_subdirectory_hierarchy(self, tmp_path):
        sub = tmp_path / "season1"
        sub.mkdir()
        input_file = sub / "clip.mp4"
        input_file.touch()
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        wav = tmp_path / "clip.wav"
        wav.write_bytes(b"wav")
        result = make_result("nested")

        with (
            patch("vtext_client.batch.extract_wav", return_value=wav),
            patch("vtext_client.batch.maybe_compress", return_value=(wav, None)),
            patch("vtext_client.batch.submit_job", return_value="job1"),
            patch("vtext_client.batch.stream_progress", return_value=result),
        ):
            out_path = _process_one(
                input_file,
                base_dir=tmp_path,
                text_dir=text_dir,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
            )

        assert out_path == tmp_path / "text" / "season1" / "clip_raw.txt"
        assert out_path.read_text(encoding="utf-8") == "nested"


class TestBatchTranscribe:
    def test_empty_directory(self, tmp_path, capsys):

        # batch_transcribe uses click.echo, which writes to stderr
        batch_transcribe(
            tmp_path,
            server="http://localhost:8000",
            fmt="txt",
            language=None,
            model=None,
            jobs=1,
        )
        # Should not raise; just prints a message

    def test_finds_media_files(self, tmp_path):
        (tmp_path / "clip1.mp4").touch()
        (tmp_path / "clip2.mp3").touch()
        (tmp_path / "notes.txt").touch()  # should be ignored

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path)
            # Return a fake output path
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(
                tmp_path,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=1,
            )

        names = {p.name for p in processed}
        assert "clip1.mp4" in names
        assert "clip2.mp3" in names
        assert "notes.txt" not in names

    def test_ignores_non_media_files(self, tmp_path):
        (tmp_path / "readme.md").touch()
        (tmp_path / "data.json").touch()

        processed = []
        with patch(
            "vtext_client.batch._process_one",
            side_effect=lambda p, **kw: processed.append(p),
        ):
            batch_transcribe(
                tmp_path,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=1,
            )

        assert processed == []

    def test_parallel_jobs(self, tmp_path):
        for i in range(4):
            (tmp_path / f"clip{i}.mp4").touch()

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path.name)
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(
                tmp_path,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=2,
            )

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
            batch_transcribe(
                tmp_path,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=1,
            )

    def test_recurses_into_subdirectories(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.mp4").touch()

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path)
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(
                tmp_path,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=1,
            )

        assert any(p.name == "nested.mp4" for p in processed)

    def test_does_not_reprocess_text_outputs(self, tmp_path):
        (tmp_path / "clip.mp4").touch()
        text_dir = tmp_path / "text"
        text_dir.mkdir()
        (text_dir / "clip.txt").write_text("old output")  # stale output: ignore
        (text_dir / "stale.mp4").write_bytes(b"fake media")  # media in text/: ignore

        processed = []

        def fake_process(path, **kwargs):
            processed.append(path.name)
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(
                tmp_path,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=1,
            )

        assert processed == ["clip.mp4"]

    def test_custom_output_dir_mirrors_hierarchy(self, tmp_path):
        sub = tmp_path / "input" / "season1"
        sub.mkdir(parents=True)
        (sub / "clip.mp4").touch()
        output_dir = tmp_path / "output"

        call_kwargs = {}

        def fake_process(path, **kwargs):
            call_kwargs.update(kwargs)
            return path.with_suffix(".txt")

        with patch("vtext_client.batch._process_one", side_effect=fake_process):
            batch_transcribe(
                tmp_path / "input",
                output_dir=output_dir,
                server="http://localhost:8000",
                fmt="txt",
                language=None,
                model=None,
                jobs=1,
            )

        # _process_one called with text_dir=output_dir, base_dir=input
        assert call_kwargs["text_dir"] == output_dir
        assert call_kwargs["base_dir"] == tmp_path / "input"


class TestBatchProgress:
    def test_non_tty_prints_milestones_only(self):
        import io

        buf = io.StringIO()
        prog = BatchProgress(["a.mp4", "b.mp4"], stream=buf)
        assert not prog.isatty
        prog.start()
        prog.update(0, 50)  # must NOT spam per-percent lines in non-tty
        prog.file_done(0, ok=True, out_name="a.txt")
        prog.file_done(1, ok=False, error="boom")
        prog.finish()
        out = buf.getvalue()
        assert "Transcribing 2 file(s)" in out
        assert "50%" not in out
        assert "Done (1/2): a.mp4 -> a.txt" in out
        assert "Failed (2/2): b.mp4: boom" in out

    def test_tty_renders_two_lines_and_tracks_overall(self):
        class _FakeTTY:
            def __init__(self):
                self.buf = []

            def write(self, s):
                self.buf.append(s)

            def flush(self):
                pass

            def isatty(self):
                return True

        stream = _FakeTTY()
        prog = BatchProgress(["a.mp4", "b.mp4"], stream=stream, min_interval=0)
        assert prog.isatty
        prog.start()
        prog.update(0, 50)
        prog.file_done(0, ok=True, out_name="a.txt")
        prog.finish()
        out = "".join(stream.buf)
        assert "当前:" in out
        assert "总进度" in out
        assert "50%" in out  # current file's pct on line 1
        assert "100%" in out  # finished file shows 100%
        assert out.count("\033[2A") >= 1  # redraws in place after first frame
