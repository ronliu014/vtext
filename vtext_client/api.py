"""HTTP client for vtext-server."""
import time
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
RETRY_BACKOFF = [1, 2, 4]  # seconds


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
            with wav_path.open("rb") as f:
                resp = requests.post(
                    url,
                    data=data,
                    files={"file": (wav_path.name, f, "application/octet-stream")},
                    timeout=timeout,
                )
            break
        except requests.ConnectionError as e:
            if attempt == MAX_RETRIES:
                raise ServerConnectionError(
                    f"Cannot connect to vtext-server at {server_url}\n\n"
                    "Possible solutions:\n"
                    "  1. Start the server: vtext-server\n"
                    f"  2. Check server status: curl {server_url}/health\n"
                    f"  3. Specify a different server: vtext --server <url>"
                ) from e
            time.sleep(wait)
        except requests.Timeout as e:
            if attempt == MAX_RETRIES:
                raise TimeoutError(f"Request to {url} timed out") from e
            time.sleep(wait)

    if resp.status_code == 429:
        body = resp.json()
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
    """Connect to SSE stream and block until done. Returns TranscriptionResult."""
    url = f"{server_url.rstrip('/')}/jobs/{job_id}/stream"

    try:
        with requests.get(url, stream=True, timeout=3600) as resp:
            if resp.status_code != 200:
                raise ServerError(f"SSE stream returned {resp.status_code}")
            for line in _iter_sse_lines(resp):
                event, data = line
                if event == "processing" and on_progress:
                    on_progress(data.get("progress", 0))
                elif event == "done":
                    return _parse_result(data)
                elif event == "error":
                    raise ServerError(data.get("message", "Unknown server error"))
    except requests.ConnectionError as e:
        raise ServerConnectionError(f"SSE connection lost: {e}") from e

    raise ServerError("SSE stream closed without a result")


def check_health(server_url: str, timeout: int = 5) -> dict:
    try:
        resp = requests.get(f"{server_url.rstrip('/')}/health", timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError as e:
        raise ServerConnectionError(
            f"Cannot connect to vtext-server at {server_url}"
        ) from e


def submit_llm_job(
    server_url: str,
    model: str,
    messages: list[dict],
    options: dict | None = None,
    timeout: int = 30,
) -> str:
    """Submit an LLM chat job to the server relay (POST /llm/chat). Returns job_id.

    Raises ServerConnectionError, QueueFullError (HTTP 429), or ServerError.
    """
    url = f"{server_url.rstrip('/')}/llm/chat"
    payload: dict = {"model": model, "messages": messages}
    if options:
        payload["options"] = options
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.ConnectionError as e:
        raise ServerConnectionError(
            f"Cannot connect to vtext-server LLM relay at {server_url}"
        ) from e
    except requests.Timeout as e:
        raise TimeoutError(f"Request to {url} timed out") from e

    if resp.status_code == 429:
        body = resp.json()
        raise QueueFullError(
            f"LLM relay queue is full ({body.get('queue_size')} jobs).",
            queue_size=body.get("queue_size", 0),
            estimated_wait=body.get("estimated_wait_seconds", 0),
        )
    if resp.status_code != 201:
        raise ServerError(f"Server returned {resp.status_code}: {resp.text}")
    return resp.json()["job_id"]


def stream_llm_result(
    server_url: str,
    job_id: str,
    on_progress: Callable[[int], None] | None = None,
) -> str:
    """Stream an LLM relay job via SSE; block until done. Returns the result text."""
    url = f"{server_url.rstrip('/')}/llm/chat/{job_id}/stream"
    try:
        with requests.get(url, stream=True, timeout=3600) as resp:
            if resp.status_code != 200:
                raise ServerError(f"SSE stream returned {resp.status_code}")
            for line in _iter_sse_lines(resp):
                event, data = line
                if event == "processing" and on_progress:
                    on_progress(data.get("progress", 0))
                elif event == "done":
                    return data.get("result", "")
                elif event == "error":
                    raise ServerError(data.get("message", "Unknown server error"))
    except requests.ConnectionError as e:
        raise ServerConnectionError(f"SSE connection lost: {e}") from e

    raise ServerError("SSE stream closed without a result")


def _iter_sse_lines(resp: requests.Response) -> Iterator[tuple[str, dict]]:
    import json
    event = "message"
    for raw in resp.iter_lines(decode_unicode=True):
        if raw.startswith("event:"):
            event = raw[6:].strip()
        elif raw.startswith("data:"):
            data = json.loads(raw[5:].strip())
            yield event, data
            event = "message"


def _parse_result(data: dict) -> TranscriptionResult:
    segments = [
        Segment(start=s["start"], end=s["end"], text=s["text"])
        for s in data.get("segments", [])
    ]
    result = TranscriptionResult(
        text=data.get("text", ""),
        language=data.get("language", ""),
        duration=data.get("duration", 0.0),
        segments=segments,
        source=data.get("source"),
        formatted=data.get("formatted"),
    )
    return result
