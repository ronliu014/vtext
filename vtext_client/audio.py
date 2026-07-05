"""Audio extraction and compression for the client."""
import shutil
import subprocess
import tempfile
from pathlib import Path

import zstandard as zstd

from .errors import VtextClientError

COMPRESS_THRESHOLD = 100 * 1024 * 1024  # 100MB


def extract_wav(input_path: Path) -> Path:
    """Extract audio from any video/audio file to a 16kHz mono WAV.

    Returns a Path to a temp file; caller is responsible for deletion.
    """
    _check_ffmpeg()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    out = Path(tmp.name)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        out.unlink(missing_ok=True)
        raise VtextClientError(
            f"ffmpeg failed to extract audio from {input_path.name}:\n{result.stderr}"
        )
    return out


def maybe_compress(wav_path: Path) -> tuple[Path, str | None]:
    """Compress wav_path with zstd if it exceeds the threshold.

    Returns (path_to_upload, encoding) where encoding is 'zstd' or None.
    """
    if wav_path.stat().st_size < COMPRESS_THRESHOLD:
        return wav_path, None

    tmp = tempfile.NamedTemporaryFile(suffix=".wav.zst", delete=False)
    tmp.close()
    out = Path(tmp.name)

    cctx = zstd.ZstdCompressor(level=3)
    with wav_path.open("rb") as src, out.open("wb") as dst:
        cctx.copy_stream(src, dst)

    return out, "zstd"


def _check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise VtextClientError(
            "ffmpeg not found. Install it first:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )
