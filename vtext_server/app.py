"""FastAPI application."""
import logging
import queue
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import zstandard as zstd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from vtext_common.types import JobStatus
from .config import ServerConfig
from .errors import ModelNotFoundError
from .models import list_available, list_cached, resolve_model_path, download
from .llm_queue import LlmQueue
from .queue import TranscriptionQueue

logger = logging.getLogger("vtext.app")

_tqueue: TranscriptionQueue | None = None
_llm_queue: LlmQueue | None = None
_config: ServerConfig | None = None


def create_app(config: ServerConfig | None = None) -> FastAPI:
    global _config, _tqueue, _llm_queue
    _config = config or ServerConfig()
    _tqueue = TranscriptionQueue(_config)
    _llm_queue = LlmQueue(_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("worker pool starting workers=%d model=%s", _config.workers, _config.model)
        _tqueue.start()
        _llm_queue.start()
        yield
        logger.info("worker pool stopping")
        _tqueue.stop()
        _llm_queue.stop()

    app = FastAPI(title="vtext-server", lifespan=lifespan)
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
        import time as _time
        t0 = _time.monotonic()

        # Validate format
        if format not in ("txt", "srt", "vtt"):
            raise HTTPException(400, "format must be txt, srt, or vtt")

        # Check file size
        content = await file.read()
        file_size = len(content)
        if file_size > _config.max_file_size:
            logger.warning("rejected oversized file filename=%s size=%d", file.filename, file_size)
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
            logger.error("failed to process upload filename=%s error=%s", file.filename, e)
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
            logger.warning("queue full size=%d filename=%s", size, file.filename)
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

        elapsed = _time.monotonic() - t0
        logger.info(
            "job queued job_id=%s filename=%s size=%d encoding=%s language=%s model=%s "
            "format=%s position=%d elapsed=%.3fs",
            job_id, file.filename, file_size, encoding or "none",
            language or "auto", model or "default", format, position, elapsed,
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

    # ---- LLM relay: generic Ollama proxy via a serialized queue ----
    @router.post("/llm/chat", status_code=201)
    async def llm_chat(body: dict):
        model = body.get("model")
        messages = body.get("messages")
        if not model or not isinstance(messages, list):
            raise HTTPException(
                400, "body must include string 'model' and list 'messages'"
            )
        options = body.get("options")
        try:
            job_id, position = _llm_queue.submit(model, messages, options)
        except queue.Full:
            size = _llm_queue.queue_size()
            logger.warning("llm queue full size=%d", size)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "QueueFull",
                    "message": "LLM relay queue is full",
                    "queue_size": size,
                    "position": size,
                    "estimated_wait_seconds": size * 60,
                },
            )
        logger.info(
            "llm job queued job_id=%s model=%s msgs=%d position=%d",
            job_id, model, len(messages), position,
        )
        return {"job_id": job_id, "status": "queued", "position": position}

    @router.get("/llm/chat/{job_id}/stream")
    async def llm_chat_stream(job_id: str):
        if _llm_queue.get_job(job_id) is None:
            raise HTTPException(404, f"Job {job_id!r} not found")

        async def event_generator():
            import json
            while True:
                job = _llm_queue.get_job(job_id)
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
                    yield {"event": "done", "data": json.dumps({"result": job["result"]})}
                    break
                elif status == JobStatus.ERROR:
                    yield {
                        "event": "error",
                        "data": json.dumps({"message": job["error"]}),
                    }
                    break
                await asyncio.sleep(0.5)

        return EventSourceResponse(event_generator())

    @router.get("/llm/chat/{job_id}")
    async def llm_chat_status(job_id: str):
        job = _llm_queue.get_job(job_id)
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
        from importlib.metadata import version as pkg_version
        return {
            "status": "ok",
            "version": pkg_version("vtext"),
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
            "llm": {
                "workers": {
                    "total": _config.llm_workers,
                    "busy": _llm_queue.busy_workers(),
                },
                "queue": {
                    "size": _llm_queue.queue_size(),
                    "max": _config.llm_queue_max,
                },
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
