"""Compatibility tests for the vision-managed qwen-general gateway."""

import queue
from unittest.mock import MagicMock, patch

import pytest
import requests

from vtext_common.types import JobStatus
from vtext_server.config import ServerConfig
from vtext_server.llm_client import (
    LlmChatResult,
    LlmUpstreamError,
    build_chat_payload,
    chat_payload_size,
    normalize_request_id,
    ollama_chat,
)
from vtext_server.llm_worker import llm_worker_loop


def make_response(status=200, body=None, request_id="gateway-id"):
    response = MagicMock()
    response.status_code = status
    response.headers = {"X-Request-ID": request_id}
    response.text = ""
    response.json.return_value = (
        body if body is not None else {"message": {"content": "complete"}, "done": True}
    )
    return response


def test_chat_sends_non_streaming_payload_and_request_id():
    response = make_response()
    with patch("vtext_server.llm_client.requests.post", return_value=response) as post:
        result = ollama_chat(
            "http://gateway:7866",
            "qwen3.6:latest",
            [{"role": "user", "content": "hello"}],
            request_id="client-id",
        )

    assert result == LlmChatResult(
        content="complete",
        request_id="gateway-id",
        status_code=200,
        elapsed_seconds=result.elapsed_seconds,
    )
    kwargs = post.call_args.kwargs
    assert kwargs["headers"] == {"X-Request-ID": "client-id"}
    assert kwargs["json"]["stream"] is False
    assert kwargs["json"]["think"] is False


def test_request_id_normalization_matches_gateway_contract():
    assert normalize_request_id("x" * 128) == "x" * 128
    for invalid in (None, "", "x" * 129):
        normalized = normalize_request_id(invalid)
        assert len(normalized) == 32
        assert normalized == normalized.lower()
        assert all(char in "0123456789abcdef" for char in normalized)


@pytest.mark.parametrize("status", [413, 503])
def test_gateway_http_errors_keep_status_and_request_id(status):
    response = make_response(
        status,
        {"error": "request_too_large" if status == 413 else "runtime_unavailable"},
    )
    with patch("vtext_server.llm_client.requests.post", return_value=response):
        with pytest.raises(LlmUpstreamError) as exc_info:
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
            )

    error = exc_info.value
    assert error.status_code == status
    assert error.request_id == "gateway-id"
    assert error.error_source == "gateway"
    assert f"HTTP {status}" in str(error)


def test_timeout_is_structured_failure():
    with patch(
        "vtext_server.llm_client.requests.post",
        side_effect=requests.Timeout("read deadline"),
    ):
        with pytest.raises(LlmUpstreamError) as exc_info:
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
                request_id="timeout-id",
            )

    assert exc_info.value.error_code == "upstream_timeout"
    assert exc_info.value.request_id == "timeout-id"


def test_transport_failure_is_structured_failure():
    with patch(
        "vtext_server.llm_client.requests.post",
        side_effect=requests.ConnectionError("connection reset"),
    ):
        with pytest.raises(LlmUpstreamError) as exc_info:
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
                request_id="transport-id",
            )

    assert exc_info.value.error_code == "upstream_transport_error"
    assert exc_info.value.request_id == "transport-id"


def test_malformed_json_never_completes():
    response = make_response()
    response.json.side_effect = ValueError("invalid JSON")
    with patch("vtext_server.llm_client.requests.post", return_value=response):
        with pytest.raises(LlmUpstreamError) as exc_info:
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
            )

    assert exc_info.value.error_code == "invalid_upstream_response"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": {}, "done": True},
        {"message": {"content": ""}, "done": True},
        {"message": {"content": None}, "done": True},
    ],
)
def test_incomplete_or_empty_body_never_completes(body):
    response = make_response(body=body)
    with patch("vtext_server.llm_client.requests.post", return_value=response):
        with pytest.raises(LlmUpstreamError):
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
            )


def test_success_response_must_report_done_true():
    response = make_response(body={"message": {"content": "partial"}, "done": False})
    with patch("vtext_server.llm_client.requests.post", return_value=response):
        with pytest.raises(LlmUpstreamError) as exc_info:
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
            )

    assert exc_info.value.error_code == "incomplete_upstream_response"


def test_proxied_ollama_error_keeps_ollama_source():
    response = make_response(500, {"error": "model exploded"})
    with patch("vtext_server.llm_client.requests.post", return_value=response):
        with pytest.raises(LlmUpstreamError) as exc_info:
            ollama_chat(
                "http://gateway:7866",
                "qwen3.6:latest",
                [{"role": "user", "content": "hello"}],
            )

    assert exc_info.value.error_code == "model exploded"
    assert exc_info.value.error_source == "ollama"


def test_payload_size_counts_utf8_and_gateway_fields():
    size = chat_payload_size(
        "qwen3.6:latest",
        [{"role": "user", "content": "\u4e2d\u6587"}],
        {"temperature": 0.4},
    )
    assert size > len("\u4e2d\u6587".encode("utf-8"))
    assert size < 2 * 1024 * 1024


def test_payload_size_matches_requests_serialized_body():
    model = "qwen3.6:latest"
    messages = [{"role": "user", "content": "\u4e2d\u6587 and ASCII"}]
    options = {"temperature": 0.4}
    payload = build_chat_payload(model, messages, options)
    prepared = requests.Request(
        "POST", "http://gateway:7866/api/chat", json=payload
    ).prepare()

    assert isinstance(prepared.body, bytes)
    assert chat_payload_size(model, messages, options) == len(prepared.body)


def test_worker_classifies_unexpected_relay_failure_as_vtext():
    task_queue = queue.Queue()
    task_queue.put("job-id")
    task_queue.put(None)
    jobs = {
        "job-id": {
            "request_id": "worker-id",
            "model": "qwen3.6:latest",
            "messages": [{"role": "user", "content": "hello"}],
            "options": None,
            "status": JobStatus.QUEUED,
            "progress": 0,
            "upstream_status_code": None,
        }
    }

    with patch(
        "vtext_server.llm_worker.ollama_chat",
        side_effect=RuntimeError("worker failure"),
    ):
        llm_worker_loop(task_queue, jobs, ServerConfig())

    assert jobs["job-id"]["status"] == JobStatus.ERROR
    assert jobs["job-id"]["upstream_error_code"] == "relay_internal_error"
    assert jobs["job-id"]["upstream_error_source"] == "vtext"
