"""Client compatibility tests for bounded refine and relay failures."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from vtext_client.api import stream_llm_result, submit_llm_job
from vtext_client.errors import RefineError, ServerConnectionError, ServerError
from vtext_client.refine import (
    CORRECT_SYSTEM_PROMPT,
    STRUCTURE_SYSTEM_PROMPT,
    _split_text,
    refine_text,
)

OPTS = {
    "ollama_url": "http://ollama:11434",
    "model": "qwen3.6:latest",
    "server_url": "http://server:8000",
    "mode": "server",
    "timeout": 900,
}


def sse_response(lines):
    response = MagicMock()
    response.status_code = 200
    response.iter_lines.return_value = iter(lines)
    response.__enter__ = lambda obj: obj
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_split_text_bounds_chunks_and_preserves_order():
    source = "first sentence. second sentence. third sentence."
    chunks = _split_text(source, max_chars=18)

    assert len(chunks) >= 3
    assert all(len(chunk) <= 18 for chunk in chunks)
    cursor = 0
    for chunk in chunks:
        position = source.find(chunk, cursor)
        assert position >= cursor
        cursor = position + len(chunk)


def test_long_refine_corrects_and_structures_every_bounded_chunk():
    calls = []

    def fake_dispatch(messages, **kwargs):
        stage = messages[0]["content"]
        source = messages[1]["content"]
        calls.append((stage, source))
        return f"done:{source}"

    with patch("vtext_client.refine._dispatch", side_effect=fake_dispatch):
        clean, summary = refine_text("a" * 25, chunk_chars=10, **OPTS)

    correction_calls = [call for call in calls if call[0] == CORRECT_SYSTEM_PROMPT]
    structure_calls = [call for call in calls if call[0] == STRUCTURE_SYSTEM_PROMPT]
    assert [len(call[1]) for call in correction_calls] == [10, 10, 5]
    assert len(structure_calls) == 3
    assert clean.count("done:") == 3
    assert summary.count("done:done:") == 3


def test_chunk_failure_aborts_complete_refine_result():
    count = 0

    def fail_second_correction(messages, **kwargs):
        nonlocal count
        if messages[0]["content"] == CORRECT_SYSTEM_PROMPT:
            count += 1
            if count == 2:
                raise ServerError("upstream_http=503")
        return "ok"

    with patch("vtext_client.refine._dispatch", side_effect=fail_second_correction):
        with pytest.raises(RefineError, match="correction chunk 2/3"):
            refine_text("a" * 25, chunk_chars=10, **OPTS)


@pytest.mark.parametrize("status", [413, 503])
def test_submit_llm_job_surfaces_gateway_http_failures(status):
    response = MagicMock()
    response.status_code = status
    response.headers = {"X-Request-ID": "request-123"}
    response.json.return_value = {
        "detail": {
            "error": "request_too_large" if status == 413 else "runtime_unavailable",
            "message": "rejected",
            "request_id": "request-123",
            "upstream_error_source": "gateway",
        }
    }
    response.text = "rejected"

    with patch("vtext_client.api.requests.post", return_value=response):
        with pytest.raises(ServerError) as exc_info:
            submit_llm_job(
                "http://server:8000",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
            )

    message = str(exc_info.value)
    assert f"HTTP {status}" in message
    assert "request_id=request-123" in message
    assert "source=gateway" in message


def test_empty_done_event_is_not_a_success():
    response = sse_response([
        "event: done",
        'data: {"result": "", "request_id": "empty-id"}',
    ])
    with patch("vtext_client.api.requests.get", return_value=response):
        with pytest.raises(ServerError, match="empty result"):
            stream_llm_result("http://server:8000", "job-id")


def test_invalid_sse_json_is_not_a_success():
    response = sse_response([
        "event: done",
        "data: not-json",
    ])
    with patch("vtext_client.api.requests.get", return_value=response):
        with pytest.raises(ServerError, match="invalid JSON"):
            stream_llm_result("http://server:8000", "job-id")


def test_error_event_keeps_http_request_id_and_latency():
    data = {
        "message": "service runtime_unavailable",
        "request_id": "failed-id",
        "upstream_status_code": 503,
        "upstream_error_code": "runtime_unavailable",
        "upstream_error_source": "gateway",
        "upstream_elapsed_seconds": 12.5,
    }
    response = sse_response([
        "event: error",
        f"data: {json.dumps(data)}",
    ])
    with patch("vtext_client.api.requests.get", return_value=response):
        with pytest.raises(ServerError) as exc_info:
            stream_llm_result("http://server:8000", "job-id")

    message = str(exc_info.value)
    assert "upstream_http=503" in message
    assert "source=gateway" in message
    assert "request_id=failed-id" in message
    assert "latency=12.5s" in message


def test_premature_sse_transport_failure_is_not_a_success():
    response = MagicMock()
    response.status_code = 200
    response.__enter__ = lambda obj: obj
    response.__exit__ = MagicMock(return_value=False)
    response.iter_lines.side_effect = requests.exceptions.ChunkedEncodingError("truncated")

    with patch("vtext_client.api.requests.get", return_value=response):
        with pytest.raises(ServerConnectionError, match="terminated before completion"):
            stream_llm_result("http://server:8000", "job-id")
