"""Worker process: pulls jobs from queue and runs whisper.cpp."""
from pathlib import Path

from .config import ServerConfig
from .errors import TranscriptionError, ModelNotFoundError
from .models import resolve_model_path
from .queue import JobStatus
from .transcriber import transcribe
from vtext_common.formats import format_output


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
        try:
            model_name = job.get("model") or config.model
            model_path = resolve_model_path(model_name, config)

            result = transcribe(
                wav_path=wav_path,
                binary=config.whisper_binary,
                model_path=model_path,
                language=job.get("language"),
                threads=config.threads,
            )

            fmt = job.get("fmt", "txt")
            formatted = format_output(result.segments, fmt)

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
        except (TranscriptionError, ModelNotFoundError) as e:
            job["status"] = JobStatus.ERROR
            job["error"] = str(e)
        except Exception as e:
            job["status"] = JobStatus.ERROR
            job["error"] = f"Unexpected error: {e}"
        finally:
            wav_path.unlink(missing_ok=True)

        jobs[job_id] = job
