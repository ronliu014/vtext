"""whisper.cpp subprocess wrapper."""
import json
import logging
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, List

from vtext_common.types import Segment, TranscriptionResult
from .errors import DependencyError, TranscriptionError

logger = logging.getLogger("vtext.transcriber")

# Matches: "whisper_print_progress_callback: progress =  50%"
_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)%")


def transcribe(
    wav_path: Path,
    binary: str,
    model_path: Path,
    language: str | None = None,
    threads: int = 4,
    progress_callback: Callable[[int], None] | None = None,
) -> TranscriptionResult:
    """Run whisper.cpp on a WAV file and return a TranscriptionResult.

    progress_callback(pct: int) is called whenever whisper reports a new
    percentage. Falls back gracefully if progress parsing fails — transcription
    result is never affected by callback errors.
    """
    _check_binary(binary)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_json = Path(f.name)

    cmd = [
        binary,
        "--model", str(model_path),
        "--file", str(wav_path),
        "--output-json",
        "--output-file", str(output_json.with_suffix("")),
        "--threads", str(threads),
        "--print-progress",   # enables "progress = NN%" lines on stderr
    ]
    cmd += ["--language", language if language else "auto"]

    try:
        logger.debug("whisper cmd=%s", " ".join(cmd))
        t0 = time.monotonic()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        output_json.unlink(missing_ok=True)
        raise DependencyError(f"whisper.cpp binary not found: {binary}") from e

    stderr_lines: list[str] = []

    def _read_stderr() -> None:
        for line in proc.stderr:
            line = line.rstrip()
            stderr_lines.append(line)
            if progress_callback:
                m = _PROGRESS_RE.search(line)
                if m:
                    try:
                        progress_callback(int(m.group(1)))
                    except Exception:
                        pass  # callback errors must never affect transcription

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    try:
        proc.stdout.read()          # drain stdout (whisper writes nothing there)
        stderr_thread.join(timeout=3610)
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise TranscriptionError("whisper.cpp timed out")

    elapsed = time.monotonic() - t0

    if proc.returncode != 0:
        stderr_tail = "\n".join(stderr_lines[-10:])
        logger.error("whisper exited code=%d stderr=%s", proc.returncode, stderr_tail[:300])
        raise TranscriptionError(
            f"whisper.cpp exited with code {proc.returncode}",
        )

    logger.debug("whisper finished elapsed=%.1fs", elapsed)
    return _parse_output(output_json, source=wav_path.name)


def _check_binary(binary: str) -> None:
    import shutil
    if not shutil.which(binary) and not Path(binary).is_file():
        raise DependencyError(
            f"whisper.cpp binary not found: {binary!r}. "
            "Set WHISPER_CPP_BIN or pass --binary."
        )


def _parse_output(json_path: Path, source: str) -> TranscriptionResult:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise TranscriptionError(f"Failed to parse whisper.cpp output: {e}") from e
    finally:
        json_path.unlink(missing_ok=True)

    raw_segments = data.get("transcription", [])
    segments: List[Segment] = []
    for seg in raw_segments:
        offsets = seg.get("offsets", {})
        segments.append(Segment(
            start=offsets.get("from", 0) / 1000.0,
            end=offsets.get("to", 0) / 1000.0,
            text=seg.get("text", ""),
        ))

    full_text = " ".join(s.text.strip() for s in segments)
    duration = segments[-1].end if segments else 0.0
    language = data.get("result", {}).get("language", "")

    return TranscriptionResult(
        text=full_text,
        language=language,
        duration=duration,
        segments=segments,
        source=source,
    )
