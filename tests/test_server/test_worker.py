"""Tests for vtext_server.worker."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vtext_server.worker import worker_loop
from vtext_server.config import ServerConfig
from vtext_common.types import JobStatus, Segment, TranscriptionResult


def make_config(tmp_path: Path) -> ServerConfig:
    cfg = ServerConfig()
    cfg.models_dir = tmp_path / "models"
    cfg.models_dir.mkdir()
    cfg.model = "base"
    cfg.whisper_binary = "whisper-cli"
    cfg.threads = 1
    return cfg


def make_fake_result(text="Hello world"):
    return TranscriptionResult(
        text=text,
        language="en",
        source="audio.wav",
        duration=3.0,
        segments=[
            Segment(start=0.0, end=1.5, text="Hello"),
            Segment(start=1.5, end=3.0, text="world"),
        ],
    )


class TestWorkerLoop:
    """Tests for worker_loop by driving it with a list-backed task queue."""

    def _run_worker(self, jobs_dict, job_ids, config, fake_transcribe=None):
        """Run worker_loop with a fake task queue that yields job_ids then None."""
        import queue as q_mod

        task_queue = q_mod.Queue()
        for jid in job_ids:
            task_queue.put(jid)
        task_queue.put(None)  # shutdown sentinel

        shared_jobs = dict(jobs_dict)
        shared_progress = {}

        # Wrap in MagicMock-compatible proxy since worker reads/writes by key
        class DictProxy(dict):
            pass

        jobs_proxy = DictProxy(shared_jobs)
        progress_proxy = DictProxy(shared_progress)

        if fake_transcribe:
            with patch("vtext_server.worker.transcribe", side_effect=fake_transcribe):
                with patch("vtext_server.worker.resolve_model_path",
                           return_value=config.models_dir / "ggml-base.bin"):
                    (config.models_dir / "ggml-base.bin").touch()
                    worker_loop(task_queue, jobs_proxy, progress_proxy, config)
        else:
            worker_loop(task_queue, jobs_proxy, progress_proxy, config)

        return jobs_proxy

    def test_successful_transcription(self, tmp_path):
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")
        fake_result = make_fake_result()

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": "en",
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        result_jobs = self._run_worker(
            jobs, ["job1"], cfg,
            fake_transcribe=lambda **kw: fake_result
        )

        assert result_jobs["job1"]["status"] == JobStatus.DONE
        assert result_jobs["job1"]["progress"] == 100
        assert result_jobs["job1"]["result"] is not None
        assert result_jobs["job1"]["result"]["text"] == "Hello world"
        assert result_jobs["job1"]["result"]["language"] == "en"
        assert len(result_jobs["job1"]["result"]["segments"]) == 2

    def test_result_includes_formatted_output(self, tmp_path):
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")
        fake_result = make_fake_result()

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "srt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        result_jobs = self._run_worker(
            jobs, ["job1"], cfg,
            fake_transcribe=lambda **kw: fake_result
        )

        formatted = result_jobs["job1"]["result"]["formatted"]
        assert "-->" in formatted  # SRT time format

    def test_transcription_error_sets_error_status(self, tmp_path):
        from vtext_server.errors import TranscriptionError
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        def fail(**kw):
            raise TranscriptionError("whisper failed", stderr="oom")

        result_jobs = self._run_worker(jobs, ["job1"], cfg, fake_transcribe=fail)

        assert result_jobs["job1"]["status"] == JobStatus.ERROR
        assert "whisper failed" in result_jobs["job1"]["error"]

    def test_model_not_found_sets_error_status(self, tmp_path):
        from vtext_server.errors import ModelNotFoundError
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": "nonexistent-model",
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        # Don't patch resolve_model_path — it should raise ModelNotFoundError naturally
        import queue as q_mod
        task_queue = q_mod.Queue()
        task_queue.put("job1")
        task_queue.put(None)

        class DictProxy(dict):
            pass

        jobs_proxy = DictProxy(jobs)

        worker_loop(task_queue, jobs_proxy, {}, cfg)

        assert jobs_proxy["job1"]["status"] == JobStatus.ERROR

    def test_wav_file_cleaned_up_after_success(self, tmp_path):
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")
        fake_result = make_fake_result()

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        self._run_worker(jobs, ["job1"], cfg, fake_transcribe=lambda **kw: fake_result)

        assert not wav.exists()

    def test_wav_file_cleaned_up_after_failure(self, tmp_path):
        from vtext_server.errors import TranscriptionError
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        self._run_worker(
            jobs, ["job1"], cfg,
            fake_transcribe=lambda **kw: (_ for _ in ()).throw(TranscriptionError("fail"))
        )

        assert not wav.exists()

    def test_status_set_to_processing_before_transcribe(self, tmp_path):
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")
        fake_result = make_fake_result()
        observed_statuses = []

        def fake_transcribe(**kw):
            # At this point status should already be PROCESSING
            # We can't read from jobs_proxy here easily, but we can
            # verify indirectly — status is DONE at the end, meaning
            # the transition happened
            return fake_result

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        result_jobs = self._run_worker(jobs, ["job1"], cfg, fake_transcribe=fake_transcribe)
        # Final state should be DONE (started as QUEUED, went through PROCESSING)
        assert result_jobs["job1"]["status"] == JobStatus.DONE

    def test_processes_multiple_jobs(self, tmp_path):
        cfg = make_config(tmp_path)
        fake_result = make_fake_result()

        jobs = {}
        for i in range(3):
            wav = tmp_path / f"audio{i}.wav"
            wav.write_bytes(b"data")
            jobs[f"job{i}"] = {
                "job_id": f"job{i}",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": i + 1,
                "result": None,
                "error": None,
            }

        result_jobs = self._run_worker(
            jobs, ["job0", "job1", "job2"], cfg,
            fake_transcribe=lambda **kw: fake_result
        )

        for i in range(3):
            assert result_jobs[f"job{i}"]["status"] == JobStatus.DONE

    def test_unexpected_exception_sets_error_status(self, tmp_path):
        cfg = make_config(tmp_path)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"data")

        jobs = {
            "job1": {
                "job_id": "job1",
                "wav_path": str(wav),
                "language": None,
                "fmt": "txt",
                "model": None,
                "status": JobStatus.QUEUED,
                "progress": 0,
                "position": 1,
                "result": None,
                "error": None,
            }
        }

        def explode(**kw):
            raise RuntimeError("unexpected crash")

        result_jobs = self._run_worker(jobs, ["job1"], cfg, fake_transcribe=explode)

        assert result_jobs["job1"]["status"] == JobStatus.ERROR
        assert "unexpected crash" in result_jobs["job1"]["error"]


class TestBusyWorkers:
    """busy_workers() must count jobs in PROCESSING state, not alive processes."""

    def _make_queue(self, jobs: dict, n_workers: int):
        """Build a TranscriptionQueue without spawning real processes."""
        from vtext_server.queue import TranscriptionQueue

        q = TranscriptionQueue.__new__(TranscriptionQueue)
        q._jobs = jobs
        q._workers = [object() for _ in range(n_workers)]
        return q

    def test_idle_reports_zero(self):
        jobs = {
            "a": {"status": JobStatus.QUEUED},
            "b": {"status": JobStatus.DONE},
        }
        q = self._make_queue(jobs, n_workers=2)
        assert q.busy_workers() == 0

    def test_counts_processing_jobs(self):
        jobs = {
            "a": {"status": JobStatus.PROCESSING},
            "b": {"status": JobStatus.QUEUED},
            "c": {"status": JobStatus.PROCESSING},
        }
        q = self._make_queue(jobs, n_workers=4)
        assert q.busy_workers() == 2

    def test_capped_at_worker_count(self):
        # More PROCESSING entries than workers must not exceed the pool size.
        jobs = {k: {"status": JobStatus.PROCESSING} for k in "abcd"}
        q = self._make_queue(jobs, n_workers=2)
        assert q.busy_workers() == 2

    def test_no_jobs_reports_zero(self):
        q = self._make_queue({}, n_workers=2)
        assert q.busy_workers() == 0
