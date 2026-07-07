"""Tests for vBook integration manifests."""

import json

from vtext_client.manifest import write_lesson_manifest


def test_write_lesson_manifest_records_outputs_and_errors(tmp_path):
    output_dir = tmp_path / "lesson"
    output_dir.mkdir()

    manifest_path = write_lesson_manifest(
        output_dir,
        source_video=tmp_path / "course" / "series" / "lesson.mp4",
        course="course",
        series="series",
        lesson_title="lesson",
        language="zh",
        status="done",
        outputs={"raw_txt": "transcript.raw.txt"},
        models={"asr": "small", "refine": "qwen3.5:9b"},
        errors=[{"stage": "refine", "code": "refine_error", "message": "skipped"}],
        started_at="2026-07-07T00:00:00Z",
        finished_at="2026-07-07T00:00:02Z",
        duration_seconds=2.0,
    )

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1"
    assert data["project"] == "vtext"
    assert data["source_video"].endswith("lesson.mp4")
    assert data["status"] == "done"
    assert data["outputs"] == {"raw_txt": "transcript.raw.txt"}
    assert data["errors"][0]["stage"] == "refine"

