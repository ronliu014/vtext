"""Worker process for serialized LLM relay jobs."""

import logging
import time

from vtext_common.types import JobStatus
from .config import ServerConfig
from .llm_client import LlmChatResult, LlmUpstreamError, ollama_chat

logger = logging.getLogger("vtext.llm_worker")


def llm_worker_loop(task_queue, jobs, config: ServerConfig) -> None:
    """Consume relay jobs and write validated results back to shared state."""
    while True:
        job_id = task_queue.get()
        if job_id is None:
            break

        job = dict(jobs[job_id])
        job["status"] = JobStatus.PROCESSING
        jobs[job_id] = job

        model = job.get("model") or config.llm_model
        request_id = job["request_id"]
        messages = job.get("messages", [])
        options = job.get("options")

        logger.info(
            "llm job start job_id=%s request_id=%s model=%s msgs=%d",
            job_id, request_id, model, len(messages),
        )
        started = time.monotonic()

        try:
            response = ollama_chat(
                ollama_url=config.ollama_url,
                model=model,
                messages=messages,
                options=options,
                timeout=config.llm_timeout,
                request_id=request_id,
            )
            elapsed = time.monotonic() - started
            if isinstance(response, LlmChatResult):
                result = response.content
                job["request_id"] = response.request_id
                job["upstream_status_code"] = response.status_code
                job["upstream_elapsed_seconds"] = round(
                    response.elapsed_seconds, 3
                )
            else:
                # Preserve compatibility with patched/custom clients returning str.
                result = response
                job["upstream_status_code"] = 200
                job["upstream_elapsed_seconds"] = round(elapsed, 3)

            if not isinstance(result, str) or not result.strip():
                raise LlmUpstreamError(
                    "upstream chat returned empty assistant content",
                    request_id=job["request_id"],
                    error_code="empty_upstream_response",
                    error_source="ollama",
                    status_code=job["upstream_status_code"],
                    elapsed_seconds=elapsed,
                )

            job["status"] = JobStatus.DONE
            job["progress"] = 100
            job["result"] = result
            logger.info(
                "llm job done job_id=%s request_id=%s model=%s "
                "http_status=%s elapsed=%.1fs chars=%d",
                job_id, job["request_id"], model,
                job["upstream_status_code"], elapsed, len(result),
            )

        except LlmUpstreamError as exc:
            elapsed = time.monotonic() - started
            job["status"] = JobStatus.ERROR
            job["request_id"] = exc.request_id
            job["error"] = str(exc)
            job["upstream_status_code"] = exc.status_code
            job["upstream_error_code"] = exc.error_code
            job["upstream_error_source"] = exc.error_source
            job["upstream_elapsed_seconds"] = round(
                exc.elapsed_seconds or elapsed, 3
            )
            logger.exception(
                "llm job upstream error job_id=%s request_id=%s model=%s "
                "http_status=%s error_code=%s elapsed=%.1fs",
                job_id, exc.request_id, model, exc.status_code,
                exc.error_code, elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            job["status"] = JobStatus.ERROR
            job["error"] = f"LLM relay error: {exc}"
            job["upstream_error_code"] = "relay_internal_error"
            job["upstream_error_source"] = "vtext"
            job["upstream_elapsed_seconds"] = round(elapsed, 3)
            logger.exception(
                "llm job error job_id=%s request_id=%s elapsed=%.1fs",
                job_id, request_id, elapsed,
            )

        jobs[job_id] = job
