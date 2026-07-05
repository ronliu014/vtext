"""Blocking Ollama client used by the LLM relay worker.

Kept as a separate module so tests can patch ``vtext_server.llm_worker.ollama_chat``
exactly like ``vtext_server.worker.transcribe``.
"""
import requests


def ollama_chat(
    ollama_url: str,
    model: str,
    messages: list[dict],
    options: dict | None = None,
    timeout: int = 300,
) -> str:
    """Call Ollama ``/api/chat`` (non-streaming, thinking off) and return the
    assistant message content.

    The relay is a generic forwarder: it does not strip ``<think>`` blocks or
    otherwise interpret the response. ``think=False`` means models that support
    reasoning will not emit thinking here, yielding a single clean content string.

    Raises :class:`requests.RequestException` on transport failure; the worker
    converts any exception into an ERROR job status.
    """
    url = f"{ollama_url.rstrip('/')}/api/chat"
    payload: dict = {
        "model": model,
        "messages": messages,
        "think": False,
        "stream": False,
    }
    if options:
        payload["options"] = options
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"]
