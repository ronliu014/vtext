"""HTTP contract tests for the qwen-general relay boundary."""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import vtext_server.app as app_module
from vtext_common.types import JobStatus
from vtext_server.app import create_app
from vtext_server.config import ServerConfig


@pytest.fixture
def relay_client():
    config = ServerConfig()
    config.workers = 0
    config.llm_workers = 0
    config.ollama_url = "http://vision.lingrengame.com:7866"
    config.llm_model = "qwen3.6:latest"
    config.llm_timeout = 900
    config.llm_max_request_size = 512

    app = create_app(config)
    transcription_queue = MagicMock()
    transcription_queue.busy_workers.return_value = 0
    transcription_queue.queue_size.return_value = 0
    relay_queue = MagicMock()
    relay_queue.submit.return_value = ("job12345", 1)
    relay_queue.busy_workers.return_value = 0
    relay_queue.queue_size.return_value = 0
    app_module._tqueue = transcription_queue
    app_module._llm_queue = relay_queue

    with TestClient(app) as client:
        yield client, relay_queue


def test_health_exposes_active_gateway_contract(relay_client):
    client, _ = relay_client
    body = client.get("/health").json()

    assert body["llm"] == {
        "upstream_url": "http://vision.lingrengame.com:7866",
        "model": "qwen3.6:latest",
        "timeout_seconds": 900,
        "request_mode": "non-streaming",
        "contract_version": "1.1.0",
        "max_request_size": 512,
        "workers": {"total": 0, "busy": 0},
        "queue": {"size": 0, "max": 16},
    }


def test_submission_echoes_request_id_and_forwards_it(relay_client):
    client, queue = relay_client
    response = client.post(
        "/llm/chat",
        headers={"X-Request-ID": "caller-id"},
        json={
            "model": "qwen3.6:latest",
            "messages": [{"role": "user", "content": "short"}],
        },
    )

    assert response.status_code == 201
    assert response.headers["X-Request-ID"] == "caller-id"
    assert response.json()["request_id"] == "caller-id"
    assert queue.submit.call_args.kwargs["request_id"] == "caller-id"


@pytest.mark.parametrize("headers", [{}, {"X-Request-ID": "x" * 129}])
def test_submission_normalizes_missing_or_oversized_request_id(
    relay_client, headers
):
    client, queue = relay_client
    response = client.post(
        "/llm/chat",
        headers=headers,
        json={
            "model": "qwen3.6:latest",
            "messages": [{"role": "user", "content": "short"}],
        },
    )

    request_id = response.json()["request_id"]
    assert response.status_code == 201
    assert response.headers["X-Request-ID"] == request_id
    assert len(request_id) == 32
    assert request_id == request_id.lower()
    assert all(char in "0123456789abcdef" for char in request_id)
    assert queue.submit.call_args.kwargs["request_id"] == request_id


def test_oversized_request_returns_413_before_queue(relay_client):
    client, queue = relay_client
    response = client.post(
        "/llm/chat",
        headers={"X-Request-ID": "large-id"},
        json={
            "model": "qwen3.6:latest",
            "messages": [{"role": "user", "content": "x" * 600}],
        },
    )

    assert response.status_code == 413
    assert response.headers["X-Request-ID"] == "large-id"
    detail = response.json()["detail"]
    assert detail["error"] == "request_too_large"
    assert detail["request_id"] == "large-id"
    queue.submit.assert_not_called()


def test_error_stream_preserves_gateway_diagnostics(relay_client):
    client, queue = relay_client
    queue.get_job.return_value = {
        "job_id": "failed",
        "request_id": "gateway-id",
        "status": JobStatus.ERROR,
        "progress": 0,
        "position": 1,
        "result": None,
        "error": "service runtime_unavailable",
        "upstream_status_code": 503,
        "upstream_error_code": "runtime_unavailable",
        "upstream_error_source": "gateway",
        "upstream_elapsed_seconds": 12.5,
    }

    response = client.get("/llm/chat/failed/stream")
    assert response.status_code == 200
    data_line = next(
        line for line in response.text.splitlines() if line.startswith("data:")
    )
    data = json.loads(data_line.split(":", 1)[1].strip())
    assert data["request_id"] == "gateway-id"
    assert data["upstream_status_code"] == 503
    assert data["upstream_error_code"] == "runtime_unavailable"
    assert data["upstream_error_source"] == "gateway"
    assert data["upstream_elapsed_seconds"] == 12.5
