"""Task queue + worker pool for the LLM relay.

Mirrors :class:`vtext_server.queue.TranscriptionQueue` but for generic Ollama
chat forwarding. It has its own ``Manager()``, ``Queue``, shared job dict, and
worker process pool, so it never contends with the transcription queue.

``llm_workers`` defaults to 1 (strict FIFO): Ollama serves one model at a time
well, and serializing forwards keeps them orderly ("不混乱") and predictable.
"""
import multiprocessing
import queue
import uuid
from typing import Any, Dict, Optional

from vtext_common.types import JobStatus


class LlmQueue:
    """Manages a multiprocessing job queue + worker pool for LLM relay."""

    def __init__(self, config):
        self._config = config
        self._manager = multiprocessing.Manager()
        self._jobs: Dict[str, Any] = self._manager.dict()
        self._task_queue: multiprocessing.Queue = multiprocessing.Queue(
            maxsize=config.llm_queue_max
        )
        self._workers = []

    def start(self) -> None:
        from .llm_worker import llm_worker_loop

        for _ in range(self._config.llm_workers):
            p = multiprocessing.Process(
                target=llm_worker_loop,
                args=(self._task_queue, self._jobs, self._config),
                daemon=True,
            )
            p.start()
            self._workers.append(p)

    def stop(self) -> None:
        for _ in self._workers:
            self._task_queue.put(None)  # one shutdown sentinel per worker
        for p in self._workers:
            p.join(timeout=5)

    def submit(self, model, messages, options) -> tuple[str, int]:
        """Enqueue an LLM job. Returns (job_id, queue_position).

        Raises :class:`queue.Full` if the queue is at capacity.
        """
        job_id = uuid.uuid4().hex[:8]
        position = self._task_queue.qsize() + 1
        job_data = {
            "job_id": job_id,
            "model": model,
            "messages": messages,
            "options": options,
            "status": JobStatus.QUEUED,
            "progress": 0,
            "position": position,
            "result": None,
            "error": None,
        }
        self._jobs[job_id] = job_data
        try:
            self._task_queue.put_nowait(job_id)
        except Exception:
            del self._jobs[job_id]
            raise queue.Full()
        return job_id, position

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)

    def queue_size(self) -> int:
        return self._task_queue.qsize()

    def busy_workers(self) -> int:
        try:
            processing = sum(
                1 for job in self._jobs.values()
                if job.get("status") == JobStatus.PROCESSING
            )
        except Exception:
            return 0
        return min(processing, len(self._workers))
