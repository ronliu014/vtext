"""Output format conversion: txt, srt, vtt."""

from typing import List
from .types import Segment


def to_txt(segments: List[Segment]) -> str:
    """Plain text output."""
    return "\n".join(s.text.strip() for s in segments)


def to_srt(segments: List[Segment]) -> str:
    """SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(seg.start)} --> {_fmt_srt_time(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def to_vtt(segments: List[Segment]) -> str:
    """WebVTT subtitle format."""
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{_fmt_vtt_time(seg.start)} --> {_fmt_vtt_time(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def format_output(segments: List[Segment], fmt: str) -> str:
    """Convert segments to the requested output format."""
    fmt = fmt.lower()
    if fmt == "srt":
        return to_srt(segments)
    elif fmt == "vtt":
        return to_vtt(segments)
    else:
        return to_txt(segments)


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
