"""Tests for vtext_common.formats."""
import pytest
from vtext_common.formats import to_txt, to_srt, to_vtt, format_output, _fmt_srt_time, _fmt_vtt_time
from vtext_common.types import Segment


def make_segments():
    return [
        Segment(start=0.0, end=1.5, text=" Hello world "),
        Segment(start=1.5, end=3.0, text=" How are you "),
    ]


class TestToTxt:
    def test_strips_whitespace(self):
        segs = [Segment(0.0, 1.0, "  hello  ")]
        assert to_txt(segs) == "hello"

    def test_joins_with_newline(self):
        segs = make_segments()
        result = to_txt(segs)
        assert result == "Hello world\nHow are you"

    def test_empty(self):
        assert to_txt([]) == ""


class TestToSrt:
    def test_structure(self):
        segs = make_segments()
        result = to_srt(segs)
        lines = result.split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert lines[2] == "Hello world"
        assert lines[3] == ""

    def test_sequence_numbers(self):
        segs = make_segments()
        result = to_srt(segs)
        lines = result.split("\n")
        assert lines[0] == "1"
        assert lines[4] == "2"

    def test_time_format(self):
        segs = [Segment(0.0, 3661.5, "test")]
        result = to_srt(segs)
        assert "00:00:00,000 --> 01:01:01,500" in result

    def test_empty(self):
        assert to_srt([]) == ""


class TestToVtt:
    def test_starts_with_webvtt(self):
        result = to_vtt([])
        assert result.startswith("WEBVTT")

    def test_structure(self):
        segs = make_segments()
        result = to_vtt(segs)
        lines = result.split("\n")
        assert lines[0] == "WEBVTT"
        assert lines[1] == ""
        assert "-->" in lines[2]
        assert lines[3] == "Hello world"

    def test_time_format_dot_separator(self):
        segs = [Segment(0.0, 3661.5, "test")]
        result = to_vtt(segs)
        assert "00:00:00.000 --> 01:01:01.500" in result


class TestFormatOutput:
    def test_txt(self):
        segs = make_segments()
        assert format_output(segs, "txt") == to_txt(segs)

    def test_srt(self):
        segs = make_segments()
        assert format_output(segs, "srt") == to_srt(segs)

    def test_vtt(self):
        segs = make_segments()
        assert format_output(segs, "vtt") == to_vtt(segs)

    def test_unknown_format_falls_back_to_txt(self):
        segs = make_segments()
        assert format_output(segs, "xml") == to_txt(segs)

    def test_case_insensitive(self):
        segs = make_segments()
        assert format_output(segs, "SRT") == to_srt(segs)


class TestTimeFormatters:
    def test_srt_zero(self):
        assert _fmt_srt_time(0.0) == "00:00:00,000"

    def test_srt_milliseconds(self):
        assert _fmt_srt_time(0.5) == "00:00:00,500"

    def test_srt_full(self):
        assert _fmt_srt_time(3661.123) == "01:01:01,123"

    def test_vtt_zero(self):
        assert _fmt_vtt_time(0.0) == "00:00:00.000"

    def test_vtt_dot_separator(self):
        assert _fmt_vtt_time(1.25) == "00:00:01.250"
