"""whisper.cpp subprocess wrapper."""
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List

from vtext_common.types import Segment, TranscriptionResult
from .errors import DependencyError, TranscriptionError

logger = logging.getLogger("vtext.transcriber")


def transcribe(
    wav_path: Path,
    binary: str,
    model_path: Path,
    language: str | None = None,
    threads: int = 4,
) -> TranscriptionResult:
    """Run whisper.cpp on a WAV file and return a TranscriptionResult."""
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
        "--no-prints",
    ]
    if language:
        cmd += ["--language", language]

    try:
        logger.debug("whisper cmd=%s", " ".join(cmd))
        t0 = time.monotonic()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
        elapsed = time.monotonic() - t0
    except subprocess.TimeoutExpired as e:
        raise TranscriptionError("whisper.cpp timed out") from e
    except FileNotFoundError as e:
        raise DependencyError(f"whisper.cpp binary not found: {binary}") from e

    if result.returncode != 0:
        logger.error("whisper exited code=%d stderr=%s", result.returncode, result.stderr[:200])
        raise TranscriptionError(
            f"whisper.cpp exited with code {result.returncode}",
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
