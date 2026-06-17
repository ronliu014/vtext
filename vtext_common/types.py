"""Shared data types for vtext client and server."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class OutputFormat(str, Enum):
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    language: str
    source: str
    duration: float
    segments: List[Segment] = field(default_factory=list)
    formatted: Optional[str] = None


@dataclass
class JobInfo:
    job_id: str
    status: JobStatus
    progress: float = 0.0          # 0.0 - 1.0
    queue_position: Optional[int] = None
    estimated_seconds: Optional[float] = None
    result: Optional[TranscriptionResult] = None
    error: Optional[str] = None


@dataclass
class QueueStatus:
    """Returned when queue is full (HTTP 429)."""
    queue_length: int
    max_queue_size: int
    active_workers: int
    max_workers: int
    estimated_wait_seconds: Optional[float] = None
