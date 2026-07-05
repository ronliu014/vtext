"""Worker process: pulls LLM jobs from the queue and forwards them to Ollama.

Module-level (not nested) so it is picklable for ``multiprocessing.Process`` on
both fork (Linux) and spawn (macOS/Windows) start methods. Mirrors
:func:`vtext_server.worker.worker_loop`, including the copy-out / write-back
idiom required for the Manager-proxied ``jobs`` dict.
"""
import logging
import time

from vtext_common.types import JobStatus
from .config import ServerConfig
from .llm_client import ollama_chat

logger = logging.getLogger("vtext.llm_worker")


def llm_worker_loop(task_queue, jobs, config: ServerConfig) -> None:
    """Run in a subprocess. Consumes job_ids; forwards each to Ollama.

    With ``llm_workers=1`` this is strictly serialized FIFO.
    """
    while True:
        job_id = task_queue.get()
        if job_id is None:  # shutdown signal
            break

        job = dict(jobs[job_id])  # copy-out from Manager proxy
        job["status"] = JobStatus.PROCESSING
        jobs[job_id] = job  # write back

        model = job.get("model") or "qwen3.5:9b"
        messages = job.get("messages", [])
        options = job.get("options")

        logger.info(
            "llm job start job_id=%s model=%s msgs=%d", job_id, model, len(messages)
        )
        t0 = time.monotonic()

        try:
            content = ollama_chat(
                ollama_url=config.ollama_url,
                model=model,
                messages=messages,
                options=options,
                timeout=config.llm_timeout,
            )
            elapsed = time.monotonic() - t0
            job["status"] = JobStatus.DONE
            job["progress"] = 100
            job["result"] = content
            logger.info(
                "llm job done job_id=%s elapsed=%.1fs chars=%d",
                job_id, elapsed, len(content),
            )

        except Exception as e:
            elapsed = time.monotonic() - t0
            job["status"] = JobStatus.ERROR
            job["error"] = f"LLM relay error: {e}"
            logger.exception("llm job error job_id=%s elapsed=%.1fs", job_id, elapsed)

        jobs[job_id] = job  # final write-back (status/result/error)
