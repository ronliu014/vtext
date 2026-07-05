"""Tests for vtext_server FastAPI app endpoints."""
import json
import queue
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from vtext_server.app import create_app
from vtext_server.config import ServerConfig
from vtext_common.types import JobStatus


def make_config(tmp_path: Path) -> ServerConfig:
    cfg = ServerConfig()
    cfg.models_dir = tmp_path / "models"
    cfg.models_dir.mkdir()
    cfg.model = "base"
    cfg.workers = 1
    cfg.queue_max = 5
    cfg.max_file_size = 500 * 1024 * 1024
    return cfg


@pytest.fixture
def mock_queue():
    q = MagicMock()
    q.submit.return_value = ("abc12345", 1)
    q.get_job.return_value = {
        "job_id": "abc12345",
        "status": JobStatus.QUEUED,
        "progress": 0,
        "position": 1,
        "result": None,
        "error": None,
    }
    q.queue_size.return_value = 0
    q.busy_workers.return_value = 0
    return q


@pytest.fixture
def client(tmp_path, mock_queue):
    cfg = make_config(tmp_path)
    app = create_app(cfg)
    # Replace the queue after creation
    import vtext_server.app as app_module
    app_module._tqueue = mock_queue
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "workers" in body
        assert "queue" in body


class TestTranscribe:
    def test_valid_wav_returns_201(self, client, tmp_path):
        wav_content = b"RIFF" + b"\x00" * 40  # minimal fake WAV
        resp = client.post(
            "/transcribe",
            data={"format": "txt"},
            files={"file": ("audio.wav", wav_content, "application/octet-stream")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "queued"

    def test_invalid_format_returns_400(self, client):
        resp = client.post(
            "/transcribe",
            data={"format": "mp3"},
            files={"file": ("audio.wav", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_queue_full_returns_429(self, client, mock_queue):
        mock_queue.submit.side_effect = queue.Full()
        mock_queue.queue_size.return_value = 5
        resp = client.post(
            "/transcribe",
            data={"format": "txt"},
            files={"file": ("audio.wav", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"]["error"] == "QueueFull"

    def test_zstd_encoded_file(self, client, tmp_path):
        import zstandard as zstd
        raw = b"RIFF" + b"\x00" * 40
        cctx = zstd.ZstdCompressor(level=3)
        compressed = cctx.compress(raw)
        resp = client.post(
            "/transcribe",
            data={"format": "txt", "encoding": "zstd"},
            files={"file": ("audio.wav.zst", compressed, "application/octet-stream")},
        )
        assert resp.status_code == 201

    def test_bad_zstd_data_returns_400(self, client):
        resp = client.post(
            "/transcribe",
            data={"format": "txt", "encoding": "zstd"},
            files={"file": ("audio.wav.zst", b"not valid zstd", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_model_not_found_returns_404(self, client, tmp_path, mock_queue):
        from vtext_server.errors import ModelNotFoundError
        with patch("vtext_server.app.resolve_model_path",
                   side_effect=ModelNotFoundError("Model 'large' not found")):
            resp = client.post(
                "/transcribe",
                data={"format": "txt", "model": "large"},
                files={"file": ("audio.wav", b"data", "application/octet-stream")},
            )
        assert resp.status_code == 404


class TestJobStatus:
    def test_existing_job(self, client):
        resp = client.get("/jobs/abc12345")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == "abc12345"

    def test_missing_job_returns_404(self, client, mock_queue):
        mock_queue.get_job.return_value = None
        resp = client.get("/jobs/notexist")
        assert resp.status_code == 404


class TestModels:
    def test_lists_models(self, client):
        resp = client.get("/models")
        assert resp.status_code == 200
        body = resp.json()
        assert "available" in body
        assert "cached" in body
        assert "current" in body

    def test_download_unknown_model_404(self, client):
        resp = client.post("/models/download", json={"name": "nonexistent-model"})
        assert resp.status_code == 404

    def test_download_missing_name_400(self, client):
        resp = client.post("/models/download", json={})
        assert resp.status_code == 400
