"""Output format helpers: txt, srt, vtt."""
from typing import List
from .types import Segment


def to_txt(segments: List[Segment]) -> str:
    return "\n".join(s.text.strip() for s in segments)


def to_srt(segments: List[Segment]) -> str:
    blocks = []
    for i, s in enumerate(segments, 1):
        start = _fmt_srt_time(s.start)
        end = _fmt_srt_time(s.end)
        blocks.append(f"{i}\n{start} --> {end}\n{s.text.strip()}")
    return "\n\n".join(blocks)


def to_vtt(segments: List[Segment]) -> str:
    blocks = ["WEBVTT"]
    for s in segments:
        start = _fmt_vtt_time(s.start)
        end = _fmt_vtt_time(s.end)
        blocks.append(f"{start} --> {end}\n{s.text.strip()}")
    return "\n\n".join(blocks)


def format_output(segments: List[Segment], fmt: str) -> str:
    if fmt == "srt":
        return to_srt(segments)
    if fmt == "vtt":
        return to_vtt(segments)
    return to_txt(segments)


def _fmt_srt_time(seconds: float) -> str:
    h, rem = divmod(int(seconds * 1000), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _fmt_vtt_time(seconds: float) -> str:
    h, rem = divmod(int(seconds * 1000), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"
