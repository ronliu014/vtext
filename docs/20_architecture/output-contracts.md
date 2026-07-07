# Output Contracts

This document defines stable artifact layouts produced by vtext. It separates
long-lived output contracts from historical integration request/response
documents.

## Legacy Single-File Layout

Without `--bundle vbook`, vtext keeps its existing single-file behavior:

```text
<input-dir>/
|-- <lesson>.mp4
|-- <lesson>_raw.<txt|srt|vtt>
|-- <lesson>_clean.txt
+-- <lesson>_summary.md
```

If `--output <dir>` is used in legacy mode, the raw transcript is written under
that directory as `<lesson>_raw.<format>`. Clean and summary files are still
written next to the source video.

## Legacy Batch Layout

Without `--output`, batch mode writes under `<input-root>/text/` and mirrors the
input hierarchy:

```text
<input-root>/
|-- <series>/
|   +-- <lesson>.mp4
+-- text/
    +-- <series>/
        |-- <lesson>_raw.srt
        |-- <lesson>_clean.txt
        +-- <lesson>_summary.md
```

With `--output <output-root>`, batch mode mirrors the input hierarchy under the
provided output root.

## vBook Per-Lesson Bundle

The stable vBook bundle is enabled explicitly:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  "<video-path>" `
  --bundle vbook `
  --output "<lesson-output-dir>" `
  --format srt `
  --language zh
```

Output:

```text
<lesson-output-dir>/
|-- transcript.raw.txt
|-- transcript.raw.srt
|-- transcript.clean.txt
|-- summary.md
+-- manifest.json
```

Rules:

- `transcript.raw.txt` is produced after successful transcription.
- `transcript.raw.srt` is produced when `--format srt` is used.
- `transcript.clean.txt` and `summary.md` are produced when refine succeeds.
- Refine failure is recorded in `manifest.json` but does not invalidate the raw
  transcript artifacts.
- Transcription failure exits non-zero and writes a failed manifest when the
  output directory can be created.

## Manifest Schema

Schema version: `1`

Required top-level fields:

```json
{
  "schema_version": "1",
  "project": "vtext",
  "source_video": "path/to/video.mp4",
  "course": "",
  "series": "",
  "lesson_title": "video",
  "language": "zh",
  "status": "done",
  "outputs": {
    "raw_txt": "transcript.raw.txt",
    "raw_srt": "transcript.raw.srt",
    "clean_txt": "transcript.clean.txt",
    "summary_md": "summary.md"
  },
  "timings": {
    "started_at": "2026-07-07T00:00:00Z",
    "finished_at": "2026-07-07T00:03:00Z",
    "duration_seconds": 180.0
  },
  "models": {
    "asr": "small",
    "refine": "qwen3.5:9b"
  },
  "errors": []
}
```

Stable statuses for the first vBook integration pass:

- `done`
- `failed`

Stable error stages:

- `audio_extraction`
- `compression`
- `transcription`
- `refine`
- `output`

Stable error codes:

- `server_connection_error`
- `queue_full`
- `server_error`
- `client_error`
- `refine_error`
- `unexpected_error`

