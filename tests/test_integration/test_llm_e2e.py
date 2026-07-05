"""End-to-end integration tests for the LLM relay (POST /llm/chat).

Spins up a real FastAPI TestClient backed by a real LlmQueue, but patches out
the actual Ollama HTTP call — mirroring tests/test_integration/test_e2e.py's
approach of "real queue + patched blocking call".
"""
import time

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from vtext_server.app import create_app
from vtext_server.config import ServerConfig


@pytest.fixture
def llm_server(tmp_path):
    """TestClient with a real LlmQueue (1 serialized worker) and a fake Ollama."""
    cfg = ServerConfig()
    cfg.workers = 0  # no transcription workers needed for LLM-only tests
    cfg.llm_workers = 1
    cfg.llm_queue_max = 4
    cfg.ollama_url = "http://fake-ollama:11434"

    with patch("vtext_server.llm_worker.ollama_chat", return_value="refined output"):
        app = create_app(cfg)
        with TestClient(app) as client:
            yield client


def submit(client, model="qwen3.5:9b", messages=None, options=None):
    return client.post(
        "/llm/chat",
        json={
            "model": model,
            "messages": messages or [{"role": "user", "content": "hi"}],
            **({"options": options} if options else {}),
        },
    )


def wait_done(client, job_id, iterations=50):
    body = {}
    for _ in range(iterations):
        body = client.get(f"/llm/chat/{job_id}").json()
        if body.get("status") == "done":
            return body
        time.sleep(0.1)
    return body


class TestSubmit:
    def test_submit_returns_job(self, llm_server):
        resp = submit(llm_server)
        assert resp.status_code == 201
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "queued"
        assert body["position"] >= 1

    def test_missing_fields_400(self, llm_server):
        assert llm_server.post("/llm/chat", json={"model": "x"}).status_code == 400
        assert llm_server.post("/llm/chat", json={"messages": []}).status_code == 400

    def test_unknown_job_404(self, llm_server):
        assert llm_server.get("/llm/chat/fakeid").status_code == 404
        assert llm_server.get("/llm/chat/fakeid/stream").status_code == 404


class TestComplete:
    def test_job_completes_via_polling(self, llm_server):
        job_id = submit(llm_server).json()["job_id"]
        body = wait_done(llm_server, job_id)
        assert body["status"] == "done"

    def test_stream_delivers_done_with_result(self, llm_server):
        job_id = submit(llm_server).json()["job_id"]
        wait_done(llm_server, job_id)

        events = []
        with llm_server.stream("GET", f"/llm/chat/{job_id}/stream") as r:
            assert r.status_code == 200
            for raw in r.iter_lines():
                line = raw if isinstance(raw, str) else raw.decode()
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
                if "done" in events or "error" in events:
                    break
        assert "done" in events


class TestQueueFull:
    def test_queue_full_returns_429(self, tmp_path):
        cfg = ServerConfig()
        cfg.workers = 0
        cfg.llm_workers = 0  # nothing drains the queue
        cfg.llm_queue_max = 1
        with patch("vtext_server.llm_worker.ollama_chat", return_value="x"):
            app = create_app(cfg)
            with TestClient(app) as client:
                assert submit(client).status_code == 201
                second = submit(client)
                assert second.status_code == 429
                assert second.json()["detail"]["error"] == "QueueFull"


class TestSerialized:
    def test_concurrency_one_serializes(self, tmp_path):
        """With llm_workers=1, jobs are processed strictly one at a time.

        Proves the "不混乱" requirement: 3 jobs x 0.4s each take >= ~1.2s total
        (serial), and /health never reports more than 1 busy worker.
        """
        cfg = ServerConfig()
        cfg.workers = 0
        cfg.llm_workers = 1
        cfg.llm_queue_max = 8

        def slow_chat(*a, **k):
            time.sleep(0.4)
            return "done"

        with patch("vtext_server.llm_worker.ollama_chat", side_effect=slow_chat):
            app = create_app(cfg)
            with TestClient(app) as client:
                ids = [submit(client).json()["job_id"] for _ in range(3)]

                t0 = time.monotonic()
                max_busy = 0
                while time.monotonic() - t0 < 5:
                    h = client.get("/health").json()
                    max_busy = max(max_busy, h["llm"]["workers"]["busy"])
                    if all(
                        client.get(f"/llm/chat/{jid}").json().get("status") == "done"
                        for jid in ids
                    ):
                        break
                    time.sleep(0.05)
                elapsed = time.monotonic() - t0

        # all finished
        for jid in ids:
            assert client.get(f"/llm/chat/{jid}").json()["status"] == "done"
        # serialized: never more than 1 busy, and total time ~ 3 * 0.4s
        assert max_busy <= 1
        assert elapsed >= 1.0  # would be ~0.4s if parallelized
