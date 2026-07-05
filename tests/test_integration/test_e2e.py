"""End-to-end integration tests.

These tests spin up a real FastAPI TestClient but mock out the actual
whisper.cpp subprocess, letting us exercise the full client→server pipeline
without needing whisper.cpp or ffmpeg installed.
"""
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from vtext_server.app import create_app
from vtext_server.config import ServerConfig
from vtext_common.types import JobStatus


FAKE_WHISPER_OUTPUT = {
    "transcription": [
        {"offsets": {"from": 0, "to": 1500}, "text": " Hello"},
        {"offsets": {"from": 1500, "to": 3000}, "text": " world"},
    ],
    "result": {"language": "en"},
}


@pytest.fixture
def server(tmp_path):
    """A TestClient with a real TranscriptionQueue backed by a fake whisper.cpp."""
    cfg = ServerConfig()
    cfg.models_dir = tmp_path / "models"
    cfg.models_dir.mkdir()
    cfg.model = "base"
    cfg.whisper_binary = str(tmp_path / "whisper-cli")
    cfg.workers = 1
    cfg.queue_max = 4
    cfg.max_file_size = 100 * 1024 * 1024
    cfg.threads = 1

    # Create a fake model file so resolve_model_path passes
    (cfg.models_dir / "ggml-base.bin").touch()

    # Patch transcribe to return a canned result instead of running whisper.cpp
    from vtext_common.types import Segment, TranscriptionResult

    fake_result = TranscriptionResult(
        text="Hello world",
        language="en",
        source="audio.wav",
        duration=3.0,
        segments=[
            Segment(start=0.0, end=1.5, text="Hello"),
            Segment(start=1.5, end=3.0, text="world"),
        ],
    )

    with patch("vtext_server.worker.transcribe", return_value=fake_result):
        app = create_app(cfg)
        with TestClient(app) as client:
            yield client


def upload_wav(client, content=None, fmt="txt", encoding=None):
    """Helper: POST /transcribe with minimal WAV content."""
    data = {"format": fmt}
    if encoding:
        data["encoding"] = encoding
    return client.post(
        "/transcribe",
        data=data,
        files={"file": ("audio.wav", content or b"RIFF" + b"\x00" * 44, "application/octet-stream")},
    )


class TestHealthEndpoint:
    def test_health_returns_ok(self, server):
        resp = server.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["workers"]["total"] == 1
        assert body["queue"]["max"] == 4


class TestModelsEndpoint:
    def test_lists_cached_model(self, server):
        resp = server.get("/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current"] == "base"
        assert "base" in body["cached"]
        assert "tiny" in body["available"]

    def test_download_unknown_model_404(self, server):
        resp = server.post("/models/download", json={"name": "nonexistent"})
        assert resp.status_code == 404

    def test_download_missing_body_400(self, server):
        resp = server.post("/models/download", json={})
        assert resp.status_code == 400


class TestTranscribeAndPoll:
    def test_submit_returns_job_id(self, server):
        resp = upload_wav(server)
        assert resp.status_code == 201
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "queued"
        assert body["position"] >= 1

    def test_invalid_format_rejected(self, server):
        resp = upload_wav(server, fmt="xml")
        assert resp.status_code == 400

    def test_job_status_endpoint(self, server):
        submit_resp = upload_wav(server)
        job_id = submit_resp.json()["job_id"]

        resp = server.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == job_id
        assert body["status"] in ("queued", "processing", "done")

    def test_unknown_job_returns_404(self, server):
        resp = server.get("/jobs/doesnotexist")
        assert resp.status_code == 404

    def test_job_completes_via_polling(self, server):
        submit_resp = upload_wav(server)
        assert submit_resp.status_code == 201
        job_id = submit_resp.json()["job_id"]

        # Poll until done (workers run in separate processes, give them time)
        for _ in range(20):
            resp = server.get(f"/jobs/{job_id}")
            body = resp.json()
            if body["status"] == "done":
                break
            time.sleep(0.2)

        assert body["status"] == "done"

    def test_zstd_compressed_upload(self, server):
        import zstandard as zstd
        raw = b"RIFF" + b"\x00" * 44
        cctx = zstd.ZstdCompressor(level=3)
        compressed = cctx.compress(raw)

        resp = upload_wav(server, content=compressed, encoding="zstd")
        assert resp.status_code == 201

    def test_file_too_large_rejected(self, server):
        # max_file_size is 100MB; send 101MB
        big = b"\x00" * (101 * 1024 * 1024)
        resp = upload_wav(server, content=big)
        assert resp.status_code == 413


class TestSseStream:
    def test_stream_delivers_done_event(self, server):
        submit_resp = upload_wav(server)
        assert submit_resp.status_code == 201
        job_id = submit_resp.json()["job_id"]

        # Wait for job to finish before reading SSE
        for _ in range(20):
            status_resp = server.get(f"/jobs/{job_id}")
            if status_resp.json()["status"] == "done":
                break
            time.sleep(0.2)

        # Now connect to stream; it should immediately yield done
        # TestClient (httpx-based) uses stream() context manager, not stream= kwarg
        events = []
        with server.stream("GET", f"/jobs/{job_id}/stream") as stream_resp:
            assert stream_resp.status_code == 200
            for raw_line in stream_resp.iter_lines():
                line = raw_line if isinstance(raw_line, str) else raw_line.decode()
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
                if "done" in events or "error" in events:
                    break

        assert "done" in events

    def test_stream_unknown_job_404(self, server):
        resp = server.get("/jobs/fakeid/stream")
        assert resp.status_code == 404


class TestQueueFull:
    def test_queue_full_returns_429(self, tmp_path):
        """A queue of max_size=1 should reject a second job."""
        cfg = ServerConfig()
        cfg.models_dir = tmp_path / "models"
        cfg.models_dir.mkdir()
        (cfg.models_dir / "ggml-base.bin").touch()
        cfg.model = "base"
        cfg.workers = 0  # no workers, so jobs pile up
        cfg.queue_max = 1

        from vtext_common.types import Segment, TranscriptionResult
        fake_result = TranscriptionResult(
            text="hi", language="en", source="a.wav", duration=1.0, segments=[]
        )
        with patch("vtext_server.worker.transcribe", return_value=fake_result):
            app = create_app(cfg)
            with TestClient(app) as client:
                # First job fills the queue
                r1 = upload_wav(client)
                assert r1.status_code == 201

                # Second job hits the limit
                r2 = upload_wav(client)
                assert r2.status_code == 429
                body = r2.json()
                assert body["detail"]["error"] == "QueueFull"


class TestOutputFormats:
    def _get_result(self, server, fmt: str) -> dict:
        submit_resp = upload_wav(server, fmt=fmt)
        job_id = submit_resp.json()["job_id"]
        for _ in range(20):
            resp = server.get(f"/jobs/{job_id}")
            body = resp.json()
            if body["status"] == "done":
                return body
            time.sleep(0.2)
        return body

    def test_txt_format(self, server):
        body = self._get_result(server, "txt")
        assert body["status"] == "done"

    def test_srt_format(self, server):
        body = self._get_result(server, "srt")
        assert body["status"] == "done"

    def test_vtt_format(self, server):
        body = self._get_result(server, "vtt")
        assert body["status"] == "done"
