"""Task queue and worker process management."""
import multiprocessing
import queue
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from vtext_common.types import JobStatus


@dataclass
class Job:
    job_id: str
    wav_path: Path
    language: Optional[str]
    fmt: str
    model: Optional[str]
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    position: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TranscriptionQueue:
    """Manages a multiprocessing job queue and worker pool."""

    def __init__(self, config):
        self._config = config
        self._manager = multiprocessing.Manager()
        self._jobs: Dict[str, Any] = self._manager.dict()
        self._progress: Dict[str, Any] = self._manager.dict()
        self._task_queue: multiprocessing.Queue = multiprocessing.Queue(
            maxsize=config.queue_max
        )
        self._workers = []

    def start(self) -> None:
        from .worker import worker_loop
        for _ in range(self._config.workers):
            p = multiprocessing.Process(
                target=worker_loop,
                args=(self._task_queue, self._jobs, self._progress, self._config),
                daemon=True,
            )
            p.start()
            self._workers.append(p)

    def stop(self) -> None:
        for _ in self._workers:
            self._task_queue.put(None)
        for p in self._workers:
            p.join(timeout=5)

    def submit(self, wav_path: Path, language, fmt, model) -> tuple[str, int]:
        """Enqueue a job. Returns (job_id, queue_position).
        Raises queue.Full if the queue is at capacity.
        """
        job_id = uuid.uuid4().hex[:8]
        position = self._task_queue.qsize() + 1
        job_data = {
            "job_id": job_id,
            "wav_path": str(wav_path),
            "language": language,
            "fmt": fmt,
            "model": model,
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
        return sum(
            1 for job in self._jobs.values()
            if job.get("status") == JobStatus.PROCESSING
        )
