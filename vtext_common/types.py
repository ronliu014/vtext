"""Shared data types for vtext client and server."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration: float
    segments: List[Segment] = field(default_factory=list)
    source: Optional[str] = None
    formatted: Optional[str] = None
