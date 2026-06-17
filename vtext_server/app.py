"""FastAPI application."""
import queue
import tempfile
from pathlib import Path

import zstandard as zstd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from .config import ServerConfig
from .errors import ModelNotFoundError, TranscriptionError
from .models import list_available, list_cached, resolve_model_path, download
from .queue import TranscriptionQueue, JobStatus

_tqueue: TranscriptionQueue | None = None
_config: ServerConfig | None = None


def create_app(config: ServerConfig | None = None) -> FastAPI:
    global _config, _tqueue
    _config = config or ServerConfig()
    _tqueue = TranscriptionQueue(_config)

    app = FastAPI(title="vtext-server")

    @app.on_event("startup")
    async def startup():
        _tqueue.start()

    @app.on_event("shutdown")
    async def shutdown():
        _tqueue.stop()

    app.include_router(_router())
    return app


def _router():
    from fastapi import APIRouter
    import time
    import asyncio

    router = APIRouter()
    _start_time = time.time()

    @router.post("/transcribe", status_code=201)
    async def transcribe(
        file: UploadFile = File(...),
        encoding: str | None = Form(None),
        language: str | None = Form(None),
        format: str = Form("txt"),
        model: str | None = Form(None),
    ):
        # Validate format
        if format not in ("txt", "srt", "vtt"):
            raise HTTPException(400, "format must be txt, srt, or vtt")

        # Check file size
        content = await file.read()
        if len(content) > _config.max_file_size:
            raise HTTPException(413, f"File exceeds {_config.max_file_size // 1024 // 1024}MB limit")

        # Write to temp file, decompress if needed
        suffix = ".wav"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp_path = Path(tmp.name)
        try:
            if encoding == "zstd":
                dctx = zstd.ZstdDecompressor()
                tmp.write(dctx.decompress(content))
            else:
                tmp.write(content)
            tmp.close()
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(400, f"Failed to process uploaded file: {e}")

        # Validate model exists
        if model:
            try:
                resolve_model_path(model, _config)
            except ModelNotFoundError as e:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(404, str(e))

        # Enqueue
        try:
            job_id, position = _tqueue.submit(tmp_path, language, format, model)
        except queue.Full:
            tmp_path.unlink(missing_ok=True)
            size = _tqueue.queue_size()
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "QueueFull",
                    "message": "Queue is full",
                    "queue_size": size,
                    "position": size,
                    "estimated_wait_seconds": size * 60,
                },
            )

        return {"job_id": job_id, "status": "queued", "position": position}

    @router.get("/jobs/{job_id}/stream")
    async def job_stream(job_id: str):
        if _tqueue.get_job(job_id) is None:
            raise HTTPException(404, f"Job {job_id!r} not found")

        async def event_generator():
            import json
            while True:
                job = _tqueue.get_job(job_id)
                if job is None:
                    break

                status = job["status"]

                if status == JobStatus.QUEUED:
                    yield {
                        "event": "queued",
                        "data": json.dumps({"position": job["position"]}),
                    }
                elif status == JobStatus.PROCESSING:
                    yield {
                        "event": "processing",
                        "data": json.dumps({"progress": job["progress"]}),
                    }
                elif status == JobStatus.DONE:
                    yield {"event": "done", "data": json.dumps(job["result"])}
                    break
                elif status == JobStatus.ERROR:
                    yield {"event": "error", "data": json.dumps({"message": job["error"]})}
                    break

                await asyncio.sleep(0.5)

        return EventSourceResponse(event_generator())

    @router.get("/jobs/{job_id}")
    async def job_status(job_id: str):
        job = _tqueue.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"Job {job_id!r} not found")
        return {
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "position": job["position"],
        }

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "uptime": int(time.time() - _start_time),
            "workers": {
                "total": _config.workers,
                "busy": _tqueue.busy_workers(),
            },
            "queue": {
                "size": _tqueue.queue_size(),
                "max": _config.queue_max,
            },
            "model": {
                "loaded": _config.model,
                "switching": False,
            },
        }

    @router.get("/models")
    async def models():
        return {
            "current": _config.model,
            "available": list_available(),
            "cached": list_cached(_config),
        }

    @router.post("/models/download")
    async def models_download(body: dict):
        name = body.get("name")
        if not name:
            raise HTTPException(400, "name is required")
        try:
            download(name, _config)
        except ModelNotFoundError as e:
            raise HTTPException(404, str(e))
        return {"status": "ok", "name": name}

    return router
