"""Tests for vtext_server.errors."""
import pytest
from vtext_server.errors import (
    VtextServerError,
    TranscriptionError,
    AudioConversionError,
    ModelNotFoundError,
    ModelLoadError,
    DependencyError,
    QueueFullError,
    JobNotFoundError,
    DecompressionError,
)


class TestErrorHierarchy:
    def test_all_inherit_from_base(self):
        for cls in [
            TranscriptionError, AudioConversionError, ModelNotFoundError,
            ModelLoadError, DependencyError, QueueFullError, JobNotFoundError,
            DecompressionError,
        ]:
            assert issubclass(cls, VtextServerError)

    def test_base_inherits_exception(self):
        assert issubclass(VtextServerError, Exception)


class TestTranscriptionError:
    def test_message(self):
        e = TranscriptionError("failed")
        assert str(e) == "failed"

    def test_default_stderr(self):
        e = TranscriptionError("failed")
        assert e.stderr == ""

    def test_stderr(self):
        e = TranscriptionError("failed", stderr="some output")
        assert e.stderr == "some output"


class TestModelNotFoundError:
    def test_message(self):
        e = ModelNotFoundError("Model 'large' not found at /models/ggml-large.bin")
        assert "large" in str(e)


class TestDependencyError:
    def test_message(self):
        e = DependencyError("whisper-cli not found")
        assert "whisper-cli" in str(e)


class TestQueueFullError:
    def test_attributes(self):
        e = QueueFullError(queue_size=10, max_size=10, estimated_wait_seconds=300.0)
        assert e.queue_size == 10
        assert e.max_size == 10
        assert e.estimated_wait_seconds == 300.0

    def test_message_contains_sizes(self):
        e = QueueFullError(5, 10, 150.0)
        assert "5" in str(e)
        assert "10" in str(e)


class TestJobNotFoundError:
    def test_attributes(self):
        e = JobNotFoundError("abc123")
        assert e.job_id == "abc123"
        assert "abc123" in str(e)
