"""HTTP client for vtext-server."""

import json
import time
import uuid
from pathlib import Path
from typing import Callable, Iterator

import requests

from vtext_common.types import Segment, TranscriptionResult
from .errors import (
    QueueFullError,
    ServerConnectionError,
    ServerError,
    TimeoutError,
)

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


def _response_detail(resp: requests.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        return {"message": resp.text[:500]}

    if not isinstance(body, dict):
        return {"message": str(body)[:500]}
    detail = body.get("detail", body)
    if isinstance(detail, dict):
        return detail
    return {"message": str(detail)[:500]}


def _relay_error_message(prefix: str, data: dict) -> str:
    parts = [prefix]
    if code := data.get("error") or data.get("upstream_error_code"):
        parts.append(f"error={code}")
    if source := data.get("upstream_error_source"):
        parts.append(f"source={source}")
    if status := data.get("upstream_status_code"):
        parts.append(f"upstream_http={status}")
    if request_id := data.get("request_id"):
        parts.append(f"request_id={request_id}")
    if latency := data.get("upstream_elapsed_seconds"):
        parts.append(f"latency={latency}s")
    if message := data.get("message"):
        parts.append(str(message))
    return "; ".join(parts)


def submit_job(
    server_url: str,
    wav_path: Path,
    encoding: str | None = None,
    language: str | None = None,
    fmt: str = "txt",
    model: str | None = None,
    timeout: int = 30,
) -> str:
    """Upload audio and return job_id. Raises on connection error or queue full."""
    url = f"{server_url.rstrip('/')}/transcribe"
    data = {"format": fmt}
    if encoding:
        data["encoding"] = encoding
    if language:
        data["language"] = language
    if model:
        data["model"] = model

    for attempt, wait in enumerate(RETRY_BACKOFF, 1):
        try:
            with wav_path.open("rb") as file_obj:
                resp = requests.post(
                    url,
                    data=data,
                    files={"file": (wav_path.name, file_obj, "application/octet-stream")},
                    timeout=timeout,
                )
            break
        except requests.ConnectionError as exc:
            if attempt == MAX_RETRIES:
                raise ServerConnectionError(
                    f"Cannot connect to vtext-server at {server_url}\n\n"
                    "Possible solutions:\n"
                    "  1. Start the server: vtext-server\n"
                    f"  2. Check server status: curl {server_url}/health\n"
                    f"  3. Specify a different server: vtext --server <url>"
                ) from exc
            time.sleep(wait)
        except requests.Timeout as exc:
            if attempt == MAX_RETRIES:
                raise TimeoutError(f"Request to {url} timed out") from exc
            time.sleep(wait)

    if resp.status_code == 429:
        body = _response_detail(resp)
        raise QueueFullError(
            f"Server queue is full ({body.get('queue_size')} jobs). "
            f"Estimated wait: {body.get('estimated_wait_seconds')}s",
            queue_size=body.get("queue_size", 0),
            estimated_wait=body.get("estimated_wait_seconds", 0),
        )
    if resp.status_code != 201:
        raise ServerError(f"Server returned {resp.status_code}: {resp.text}")

    return resp.json()["job_id"]


def stream_progress(
    server_url: str,
    job_id: str,
    on_progress: Callable[[int], None] | None = None,
) -> TranscriptionResult:
    """Connect to SSE stream and block until done."""
    url = f"{server_url.rstrip('/')}/jobs/{job_id}/stream"
    try:
        with requests.get(url, stream=True, timeout=3600) as resp:
            if resp.status_code != 200:
                raise ServerError(f"SSE stream returned {resp.status_code}")
            for event, data in _iter_sse_lines(resp):
                if event == "processing" and on_progress:
                    on_progress(data.get("progress", 0))
                elif event == "done":
                    return _parse_result(data)
                elif event == "error":
                    raise ServerError(data.get("message", "Unknown server error"))
    except requests.RequestException as exc:
        raise ServerConnectionError(f"SSE connection lost: {exc}") from exc

    raise ServerError("SSE stream closed without a result")


def check_health(server_url: str, timeout: int = 5) -> dict:
    try:
        resp = requests.get(f"{server_url.rstrip('/')}/health", timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError as exc:
        raise ServerConnectionError(
            f"Cannot connect to vtext-server at {server_url}"
        ) from exc


def submit_llm_job(
    server_url: str,
    model: str,
    messages: list[dict],
    options: dict | None = None,
    timeout: int = 30,
    request_id: str | None = None,
) -> str:
    """Submit one bounded non-streaming LLM chat job to the server relay."""
    url = f"{server_url.rstrip('/')}/llm/chat"
    correlation_id = request_id or uuid.uuid4().hex
    payload: dict = {"model": model, "messages": messages}
    if options:
        payload["options"] = options
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"X-Request-ID": correlation_id},
            timeout=timeout,
        )
    except requests.ConnectionError as exc:
        raise ServerConnectionError(
            f"Cannot connect to vtext-server LLM relay at {server_url}; "
            f"request_id={correlation_id}"
        ) from exc
    except requests.Timeout as exc:
        raise TimeoutError(
            f"Request to {url} timed out; request_id={correlation_id}"
        ) from exc

    detail = _response_detail(resp)
    detail.setdefault("request_id", resp.headers.get("X-Request-ID", correlation_id))
    if resp.status_code == 429:
        raise QueueFullError(
            _relay_error_message("LLM relay queue is full", detail),
            queue_size=detail.get("queue_size", 0),
            estimated_wait=detail.get("estimated_wait_seconds", 0),
        )
    if resp.status_code != 201:
        raise ServerError(
            _relay_error_message(
                f"LLM relay returned HTTP {resp.status_code}", detail
            )
        )

    try:
        job_id = resp.json()["job_id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ServerError(
            f"LLM relay returned an invalid submission response; "
            f"request_id={detail['request_id']}"
        ) from exc
    return job_id


def stream_llm_result(
    server_url: str,
    job_id: str,
    on_progress: Callable[[int], None] | None = None,
    timeout: int = 900,
) -> str:
    """Wait for one complete relay result; reject errors and truncated SSE."""
    url = f"{server_url.rstrip('/')}/llm/chat/{job_id}/stream"
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            if resp.status_code != 200:
                raise ServerError(f"LLM SSE stream returned HTTP {resp.status_code}")
            for event, data in _iter_sse_lines(resp):
                if event == "processing" and on_progress:
                    on_progress(data.get("progress", 0))
                elif event == "done":
                    result = data.get("result")
                    if not isinstance(result, str) or not result.strip():
                        raise ServerError(
                            _relay_error_message(
                                "LLM relay returned an empty result", data
                            )
                        )
                    return result
                elif event == "error":
                    raise ServerError(
                        _relay_error_message("LLM relay job failed", data)
                    )
    except requests.Timeout as exc:
        raise TimeoutError(f"LLM SSE stream timed out for job {job_id}") from exc
    except requests.RequestException as exc:
        raise ServerConnectionError(
            f"LLM SSE stream terminated before completion for job {job_id}: {exc}"
        ) from exc

    raise ServerError(
        f"LLM SSE stream closed without a terminal result for job {job_id}"
    )


def _iter_sse_lines(resp: requests.Response) -> Iterator[tuple[str, dict]]:
    event = "message"
    try:
        lines = resp.iter_lines(decode_unicode=True)
        for raw in lines:
            if not raw:
                continue
            if raw.startswith("event:"):
                event = raw[6:].strip()
            elif raw.startswith("data:"):
                try:
                    data = json.loads(raw[5:].strip())
                except json.JSONDecodeError as exc:
                    raise ServerError("SSE stream contained invalid JSON") from exc
                if not isinstance(data, dict):
                    raise ServerError("SSE event data must be a JSON object")
                yield event, data
                event = "message"
    except requests.RequestException:
        raise


def _parse_result(data: dict) -> TranscriptionResult:
    segments = [
        Segment(start=segment["start"], end=segment["end"], text=segment["text"])
        for segment in data.get("segments", [])
    ]
    return TranscriptionResult(
        text=data.get("text", ""),
        language=data.get("language", ""),
        duration=data.get("duration", 0.0),
        segments=segments,
        source=data.get("source"),
        formatted=data.get("formatted"),
    )
