"""Tests for vtext_common.types."""
import pytest
from vtext_common.types import (
    OutputFormat, JobStatus, Segment, TranscriptionResult, JobInfo, QueueStatus
)


class TestOutputFormat:
    def test_values(self):
        assert OutputFormat.TXT == "txt"
        assert OutputFormat.SRT == "srt"
        assert OutputFormat.VTT == "vtt"

    def test_is_str(self):
        assert isinstance(OutputFormat.TXT, str)


class TestJobStatus:
    def test_values(self):
        assert JobStatus.QUEUED == "queued"
        assert JobStatus.PROCESSING == "processing"
        assert JobStatus.DONE == "done"
        assert JobStatus.ERROR == "error"

    def test_is_str(self):
        assert isinstance(JobStatus.DONE, str)


class TestSegment:
    def test_fields(self):
        s = Segment(start=1.0, end=2.0, text="hello")
        assert s.start == 1.0
        assert s.end == 2.0
        assert s.text == "hello"


class TestTranscriptionResult:
    def test_defaults(self):
        r = TranscriptionResult(text="hi", language="en", source="test.wav", duration=1.0)
        assert r.segments == []
        assert r.formatted is None

    def test_with_segments(self):
        segs = [Segment(0.0, 1.0, "hi")]
        r = TranscriptionResult(
            text="hi", language="en", source="test.wav", duration=1.0, segments=segs
        )
        assert len(r.segments) == 1


class TestJobInfo:
    def test_defaults(self):
        j = JobInfo(job_id="abc", status=JobStatus.QUEUED)
        assert j.progress == 0.0
        assert j.queue_position is None
        assert j.estimated_seconds is None
        assert j.result is None
        assert j.error is None


class TestQueueStatus:
    def test_fields(self):
        q = QueueStatus(queue_length=5, max_queue_size=10, active_workers=2, max_workers=4)
        assert q.queue_length == 5
        assert q.estimated_wait_seconds is None
