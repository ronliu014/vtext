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
  --server "http://192.168.0.122:8000" `
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

- `--bundle vbook` always performs refine through the vtext server relay.
  The default `auto` mode is resolved to `server`; explicit `direct` mode is
  rejected for this production contract.
- `--no-refine` and a disabled client refine configuration are rejected for
  `--bundle vbook` because they cannot satisfy the required artifact layout.
- Transcripts longer than 6,000 characters use bounded server-relay calls.
  vtext splits at sentence boundaries, corrects and structures each chunk, then
  assembles the chunks in source order. This avoids one full-output request
  exceeding the server LLM timeout.
- `transcript.raw.txt` is produced after successful transcription.
- `transcript.raw.srt` is produced when `--format srt` is used.
- `transcript.clean.txt` and `summary.md` are always produced after successful
  transcription. When refine succeeds they contain LLM-corrected/structured
  text. When refine fails, vtext writes explicit fallback files derived from the
  raw transcript so the vBook bundle contract remains complete.
- Refine failure is recorded in `manifest.json` `errors[]` but does not
  invalidate the transcript artifacts or the bundle layout.
- Transcription failure exits non-zero and writes a failed manifest when the
  output directory can be created.

### Refine-Only Bundle Recovery

Recover an existing bundle without rerunning ASR:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  "<lesson-output-dir>/transcript.raw.txt" `
  --server "http://192.168.0.122:8000" `
  --refine-only `
  --bundle vbook `
  --output "<lesson-output-dir>"
```

The command requires the existing `manifest.json`. On success it writes the
canonical clean/summary files, removes active refine errors, and preserves those
errors under `recovery.previous_errors`. It does not alter the raw transcript.

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

Optional recovery audit object:

```json
{
  "recovery": {
    "mode": "chunked_refine_only",
    "source": "transcript.raw.txt",
    "chunk_chars": 6000,
    "recovered_at": "2026-07-22T03:00:00Z",
    "previous_errors": []
  }
}
```

`mode` is `refine_only` when the source fits one request and
`chunked_refine_only` when bounded chunking is used.

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
