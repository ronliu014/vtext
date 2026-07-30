"""Blocking Ollama client used by the LLM relay worker."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class LlmChatResult:
    """Validated response plus correlation metadata from the upstream gateway."""

    content: str
    request_id: str
    status_code: int
    elapsed_seconds: float


QWEN_GENERAL_OPENAPI_VERSION = "1.1.0"


GATEWAY_ERROR_CODES = {
    "network_access_denied",
    "request_too_large",
    "runtime_error",
    "runtime_timeout",
    "runtime_unavailable",
}


def normalize_request_id(request_id: str | None) -> str:
    """Apply the qwen-general 1.1.0 request-ID normalization contract."""
    if isinstance(request_id, str) and 1 <= len(request_id) <= 128:
        return request_id
    return uuid.uuid4().hex


class LlmUpstreamError(Exception):
    """Structured upstream failure safe to expose through the relay job API."""

    def __init__(
        self,
        message: str,
        *,
        request_id: str,
        error_code: str,
        error_source: str = "unknown",
        status_code: int | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.error_code = error_code
        self.error_source = error_source
        self.status_code = status_code
        self.elapsed_seconds = elapsed_seconds


def build_chat_payload(
    model: str,
    messages: list[dict],
    options: dict | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "think": False,
        "stream": False,
    }
    if options:
        payload["options"] = options
    return payload


def chat_payload_size(
    model: str,
    messages: list[dict],
    options: dict | None = None,
) -> int:
    """Return the exact JSON body size produced by the requests serializer."""
    payload = build_chat_payload(model, messages, options)
    return len(
        json.dumps(payload, allow_nan=False).encode("utf-8")
    )


def _response_error(resp: requests.Response) -> tuple[str, str, str]:
    error_code = "upstream_http_error"
    message = resp.text[:500]
    source = "unknown"
    try:
        body = resp.json()
    except ValueError:
        return error_code, message, source

    if isinstance(body, dict):
        error_code = str(body.get("error") or body.get("code") or error_code)
        detail = body.get("detail")
        if isinstance(detail, dict):
            error_code = str(detail.get("error") or detail.get("code") or error_code)
            message = str(detail.get("message") or detail)
        else:
            message = str(body.get("message") or detail or body)
        source = "gateway" if error_code in GATEWAY_ERROR_CODES else "ollama"
    return error_code, message[:500], source


def ollama_chat(
    ollama_url: str,
    model: str,
    messages: list[dict],
    options: dict | None = None,
    timeout: int = 300,
    request_id: str | None = None,
) -> LlmChatResult:
    """Call non-streaming chat and require one complete validated response."""
    url = f"{ollama_url.rstrip('/')}/api/chat"
    correlation_id = normalize_request_id(request_id)
    payload = build_chat_payload(model, messages, options)
    started = time.monotonic()

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"X-Request-ID": correlation_id},
            timeout=timeout,
        )
    except requests.Timeout as exc:
        elapsed = time.monotonic() - started
        raise LlmUpstreamError(
            f"upstream chat timed out after {elapsed:.1f}s",
            request_id=correlation_id,
            error_code="upstream_timeout",
            error_source="vtext",
            elapsed_seconds=elapsed,
        ) from exc
    except requests.RequestException as exc:
        elapsed = time.monotonic() - started
        raise LlmUpstreamError(
            f"upstream chat transport failed: {exc}",
            request_id=correlation_id,
            error_code="upstream_transport_error",
            error_source="vtext",
            elapsed_seconds=elapsed,
        ) from exc

    elapsed = time.monotonic() - started
    response_request_id = resp.headers.get("X-Request-ID") or correlation_id
    if resp.status_code != 200:
        error_code, detail, source = _response_error(resp)
        raise LlmUpstreamError(
            f"upstream chat returned HTTP {resp.status_code}: {detail}",
            request_id=response_request_id,
            error_code=error_code,
            error_source=source,
            status_code=resp.status_code,
            elapsed_seconds=elapsed,
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise LlmUpstreamError(
            f"upstream chat returned an incomplete response: {exc}",
            request_id=response_request_id,
            error_code="invalid_upstream_response",
            error_source="ollama",
            status_code=resp.status_code,
            elapsed_seconds=elapsed,
        ) from exc

    if not isinstance(body, dict) or body.get("done") is not True:
        raise LlmUpstreamError(
            "upstream chat did not report done=true",
            request_id=response_request_id,
            error_code="incomplete_upstream_response",
            error_source="ollama",
            status_code=resp.status_code,
            elapsed_seconds=elapsed,
        )

    try:
        content = body["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise LlmUpstreamError(
            f"upstream chat returned an incomplete response: {exc}",
            request_id=response_request_id,
            error_code="invalid_upstream_response",
            error_source="ollama",
            status_code=resp.status_code,
            elapsed_seconds=elapsed,
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise LlmUpstreamError(
            "upstream chat returned empty assistant content",
            request_id=response_request_id,
            error_code="empty_upstream_response",
            error_source="ollama",
            status_code=resp.status_code,
            elapsed_seconds=elapsed,
        )

    return LlmChatResult(
        content=content,
        request_id=response_request_id,
        status_code=resp.status_code,
        elapsed_seconds=elapsed,
    )
