"""Manifest helpers for stable cross-project artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1"
PROJECT = "vtext"


def write_lesson_manifest(
    output_dir: Path,
    *,
    source_video: Path,
    course: str,
    series: str,
    lesson_title: str,
    language: str | None,
    status: str,
    outputs: dict[str, str],
    models: dict[str, str],
    errors: list[dict[str, str]],
    started_at: str,
    finished_at: str,
    duration_seconds: float,
) -> Path:
    """Write a vBook-compatible per-lesson manifest and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "source_video": str(source_video),
        "course": course,
        "series": series,
        "lesson_title": lesson_title,
        "language": language or "",
        "status": status,
        "outputs": outputs,
        "timings": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
        },
        "models": models,
        "errors": errors,
    }
    path = output_dir / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def error_entry(stage: str, code: str, message: Any) -> dict[str, str]:
    """Build a stable manifest error entry."""
    return {"stage": stage, "code": code, "message": str(message)}

