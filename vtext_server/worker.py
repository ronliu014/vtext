"""Worker process: pulls jobs from queue and runs whisper.cpp."""
import logging
import time
from pathlib import Path

from vtext_common.types import JobStatus
from .config import ServerConfig
from .errors import TranscriptionError, ModelNotFoundError
from .models import resolve_model_path
from .transcriber import transcribe
from vtext_common.formats import format_output

logger = logging.getLogger("vtext.worker")


def worker_loop(task_queue, jobs, progress, config: ServerConfig) -> None:
    """Run in a subprocess. Consumes job_ids from task_queue indefinitely."""
    while True:
        job_id = task_queue.get()
        if job_id is None:  # shutdown signal
            break

        job = dict(jobs[job_id])
        job["status"] = JobStatus.PROCESSING
        jobs[job_id] = job

        wav_path = Path(job["wav_path"])
        model_name = job.get("model") or config.model
        language = job.get("language")
        fmt = job.get("fmt", "txt")

        logger.info(
            "job start job_id=%s model=%s language=%s format=%s file=%s",
            job_id, model_name, language or "auto", fmt, wav_path.name,
        )
        t0 = time.monotonic()

        try:
            model_path = resolve_model_path(model_name, config)

            result = transcribe(
                wav_path=wav_path,
                binary=config.whisper_binary,
                model_path=model_path,
                language=language,
                threads=config.threads,
            )

            formatted = format_output(result.segments, fmt)
            elapsed = time.monotonic() - t0

            job["status"] = JobStatus.DONE
            job["progress"] = 100
            job["result"] = {
                "text": result.text,
                "language": result.language,
                "duration": result.duration,
                "source": result.source,
                "formatted": formatted,
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ],
            }

            logger.info(
                "job done job_id=%s detected_language=%s duration=%.1fs elapsed=%.1fs "
                "segments=%d",
                job_id, result.language, result.duration, elapsed, len(result.segments),
            )

        except (TranscriptionError, ModelNotFoundError) as e:
            elapsed = time.monotonic() - t0
            job["status"] = JobStatus.ERROR
            job["error"] = str(e)
            logger.error("job error job_id=%s elapsed=%.1fs error=%s", job_id, elapsed, e)

        except Exception as e:
            elapsed = time.monotonic() - t0
            job["status"] = JobStatus.ERROR
            job["error"] = f"Unexpected error: {e}"
            logger.exception("job unexpected error job_id=%s elapsed=%.1fs", job_id, elapsed)

        finally:
            wav_path.unlink(missing_ok=True)

        jobs[job_id] = job
