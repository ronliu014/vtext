"""Tests for vtext_client.api."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
import requests

from vtext_client.api import submit_job, stream_progress, check_health, _iter_sse_lines, _parse_result
from vtext_client.errors import (
    QueueFullError, ServerConnectionError, ServerError, TimeoutError
)
from vtext_common.types import Segment, TranscriptionResult


class TestSubmitJob:
    def _make_wav(self, tmp_path: Path) -> Path:
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 40)
        return wav

    def test_success_returns_job_id(self, tmp_path):
        wav = self._make_wav(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"job_id": "abc12345", "status": "queued"}

        with patch("requests.post", return_value=mock_resp):
            job_id = submit_job("http://localhost:8000", wav)

        assert job_id == "abc12345"

    def test_queue_full_raises(self, tmp_path):
        wav = self._make_wav(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {
            "detail": {"queue_size": 10, "estimated_wait_seconds": 300}
        }
        mock_resp.json.return_value = {"queue_size": 10, "estimated_wait_seconds": 300}

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(QueueFullError) as exc_info:
                submit_job("http://localhost:8000", wav)

        assert exc_info.value.queue_size == 10

    def test_server_error_raises(self, tmp_path):
        wav = self._make_wav(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(ServerError):
                submit_job("http://localhost:8000", wav)

    def test_connection_error_retries_then_raises(self, tmp_path):
        wav = self._make_wav(tmp_path)
        with patch("requests.post", side_effect=requests.ConnectionError("refused")):
            with patch("time.sleep"):  # don't actually sleep in tests
                with pytest.raises(ServerConnectionError, match="Cannot connect"):
                    submit_job("http://localhost:8000", wav)

    def test_timeout_retries_then_raises(self, tmp_path):
        wav = self._make_wav(tmp_path)
        with patch("requests.post", side_effect=requests.Timeout("timed out")):
            with patch("time.sleep"):
                with pytest.raises(TimeoutError):
                    submit_job("http://localhost:8000", wav)

    def test_encoding_included_when_set(self, tmp_path):
        wav = self._make_wav(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"job_id": "xyz"}

        captured = {}

        def fake_post(url, data=None, files=None, timeout=None):
            captured["data"] = data
            return mock_resp

        with patch("requests.post", side_effect=fake_post):
            submit_job("http://localhost:8000", wav, encoding="zstd")

        assert captured["data"].get("encoding") == "zstd"

    def test_passes_language_and_model(self, tmp_path):
        wav = self._make_wav(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"job_id": "xyz"}

        captured = {}

        def fake_post(url, data=None, files=None, timeout=None):
            captured["data"] = data
            return mock_resp

        with patch("requests.post", side_effect=fake_post):
            submit_job("http://localhost:8000", wav, language="zh", model="large-v3")

        assert captured["data"]["language"] == "zh"
        assert captured["data"]["model"] == "large-v3"


class TestIterSseLines:
    def _make_response(self, lines):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        return mock_resp

    def test_parses_event_and_data(self):
        resp = self._make_response([
            "event: processing",
            'data: {"progress": 50}',
        ])
        results = list(_iter_sse_lines(resp))
        assert results == [("processing", {"progress": 50})]

    def test_default_event_is_message(self):
        resp = self._make_response(['data: {"key": "val"}'])
        results = list(_iter_sse_lines(resp))
        assert results[0][0] == "message"

    def test_resets_event_after_data(self):
        resp = self._make_response([
            "event: done",
            'data: {"text": "hi"}',
            'data: {"text": "second"}',
        ])
        results = list(_iter_sse_lines(resp))
        assert results[0] == ("done", {"text": "hi"})
        assert results[1] == ("message", {"text": "second"})

    def test_empty_stream(self):
        resp = self._make_response([])
        assert list(_iter_sse_lines(resp)) == []


class TestParseResult:
    def test_full_data(self):
        data = {
            "text": "Hello world",
            "language": "en",
            "duration": 3.0,
            "source": "test.wav",
            "formatted": "Hello world",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "Hello"},
                {"start": 1.5, "end": 3.0, "text": "world"},
            ],
        }
        result = _parse_result(data)
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration == 3.0
        assert len(result.segments) == 2
        assert result.segments[0].start == 0.0

    def test_missing_fields_use_defaults(self):
        result = _parse_result({})
        assert result.text == ""
        assert result.language == ""
        assert result.duration == 0.0
        assert result.segments == []


class TestStreamProgress:
    def _make_sse_response(self, events):
        """events: list of (event_name, data_dict)"""
        lines = []
        for event, data in events:
            lines.append(f"event: {event}")
            lines.append(f"data: {json.dumps(data)}")
            lines.append("")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = iter(
            line for line in lines if line != ""
            # filter blank lines since iter_lines skips them
        )
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_returns_result_on_done(self):
        done_data = {
            "text": "Hello",
            "language": "en",
            "duration": 1.0,
            "source": "test.wav",
            "segments": [],
        }
        mock_resp = self._make_sse_response([("done", done_data)])

        with patch("requests.get", return_value=mock_resp):
            result = stream_progress("http://localhost:8000", "abc123")

        assert result.text == "Hello"

    def test_calls_on_progress(self):
        mock_resp = self._make_sse_response([
            ("processing", {"progress": 50}),
            ("done", {"text": "", "language": "en", "duration": 0.0, "source": "", "segments": []}),
        ])

        progress_calls = []
        with patch("requests.get", return_value=mock_resp):
            stream_progress(
                "http://localhost:8000", "abc123",
                on_progress=lambda p: progress_calls.append(p)
            )

        assert 50 in progress_calls

    def test_server_error_event_raises(self):
        mock_resp = self._make_sse_response([
            ("error", {"message": "Transcription failed"}),
        ])
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(ServerError, match="Transcription failed"):
                stream_progress("http://localhost:8000", "abc123")

    def test_connection_error_raises(self):
        with patch("requests.get", side_effect=requests.ConnectionError("lost")):
            with pytest.raises(ServerConnectionError, match="SSE connection lost"):
                stream_progress("http://localhost:8000", "abc123")


class TestCheckHealth:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        with patch("requests.get", return_value=mock_resp):
            result = check_health("http://localhost:8000")
        assert result["status"] == "ok"

    def test_connection_error_raises(self):
        with patch("requests.get", side_effect=requests.ConnectionError()):
            with pytest.raises(ServerConnectionError):
                check_health("http://localhost:8000")
