# vBook Text Integration Response

Status: accepted with minimal vtext changes
Date: 2026-07-07
From: vtext
To: vBook
Related:

- `E:/projects/my_app/vbook/docs/90_reference/cross-project-coordination-notice.md`
- `E:/projects/my_app/vbook/docs/90_reference/vbook-text-integration-request.md`

## Summary

vtext accepts the proposed cross-project boundary: vBook should call vtext through
documented CLI/API/artifact contracts, not by importing or vendoring vtext source
code. vtext owns transcript extraction, ASR text correction, and text summary
generation. vBook owns course orchestration, visual evidence, evidence fusion,
preview output, and vault write-back.

This response documents the current vtext behavior and the small compatibility
extension vtext provides for vBook.

## Supported CLI Commands

Current health check:

```powershell
python -m vtext_client --check-server --server "http://192.168.0.122:8000"
```

Current single-video transcription:

```powershell
python -m vtext_client "<video-path>" --server "http://192.168.0.122:8000" --format srt --language zh
```

Current single-video transcription with explicit raw output location:

```powershell
python -m vtext_client "<video-path>" --output "<path-or-directory>" --format srt --language zh
```

Current batch transcription:

```powershell
python -m vtext_client "<input-root>" --output "<output-root>" --format srt --language zh --jobs 2
```

vBook integration command, added as the stable contract:

```powershell
python -m vtext_client "<video-path>" --server "http://192.168.0.122:8000" --bundle vbook --output "<lesson-output-dir>" --format srt --language zh
```

Notes:

- `--bundle vbook` is single-video only in the first implementation.
- `--output` must be a directory when `--bundle vbook` is used.
- `--bundle vbook` always routes refine through the vtext server. Its default
  `auto` mode resolves to `server`, and explicit `direct` mode is rejected.
- vBook should pass `--format srt` when it needs `transcript.raw.srt`.
- vtext refine must remain enabled for `--bundle vbook`; `--no-refine` and a
  disabled client refine configuration are rejected because they cannot satisfy
  the required artifact layout.

## Current Single-Video Output Layout

Without `--bundle vbook`, vtext keeps its existing layout:

```text
<input-dir>/
|-- <lesson>.mp4
|-- <lesson>_raw.<txt|srt|vtt>
|-- <lesson>_clean.txt
+-- <lesson>_summary.md
```

If `--output <dir>` is used in legacy mode, the raw transcript is written under
that directory as `<lesson>_raw.<format>`. Existing clean and summary files are
still written next to the source video. vBook should not rely on this legacy
layout as its long-term machine contract.

## vBook Bundle Output Layout

With `--bundle vbook`, vtext writes a stable per-lesson bundle:

```text
<lesson-output-dir>/
|-- transcript.raw.srt
|-- transcript.raw.txt
|-- transcript.clean.txt
|-- summary.md
+-- manifest.json
```

`transcript.raw.txt` is always produced after successful transcription.
`transcript.raw.srt` is produced when `--format srt` is used. If another format is
requested, vtext may also produce `transcript.raw.<format>`, but vBook should use
`--format srt` for the first integration pass.

`transcript.clean.txt` and `summary.md` are produced for every successful
transcription. When refine succeeds, they contain LLM-corrected and structured
text. When refine fails, vtext writes explicit fallback files derived from the
raw transcript, keeps the bundle layout complete, and records the refine error
in the manifest.

## Manifest Support

vtext provides `manifest.json` for `--bundle vbook`. Schema version is `1`.

Success example:

```json
{
  "schema_version": "1",
  "project": "vtext",
  "source_video": "F:/downloads/allwin/投资训练营/韩珂龙头班：基础篇/如何高效选股，构建自己的短线股票池.mp4",
  "course": "投资训练营",
  "series": "韩珂龙头班：基础篇",
  "lesson_title": "如何高效选股，构建自己的短线股票池",
  "language": "zh",
  "status": "done",
  "outputs": {
    "raw_srt": "transcript.raw.srt",
    "raw_txt": "transcript.raw.txt",
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

Failure example:

```json
{
  "schema_version": "1",
  "project": "vtext",
  "source_video": "path/to/video.mp4",
  "course": "",
  "series": "",
  "lesson_title": "video",
  "language": "zh",
  "status": "failed",
  "outputs": {},
  "timings": {
    "started_at": "2026-07-07T00:00:00Z",
    "finished_at": "2026-07-07T00:00:05Z",
    "duration_seconds": 5.0
  },
  "models": {
    "asr": "small",
    "refine": "qwen3.5:9b"
  },
  "errors": [
    {
      "stage": "transcription",
      "code": "server_error",
      "message": "Human-readable failure summary"
    }
  ]
}
```

Metadata defaults:

- `lesson_title` defaults to the source video stem.
- `series` defaults to the source video parent directory name.
- `course` defaults to the parent of the series directory when present.
- vBook may override these later if vtext adds explicit metadata options.

## Exit Codes And Error Model

Current CLI behavior:

- Exit `0`: command completed.
- Exit `1`: missing input, server connection failure, queue full, server error,
  or other vtext client error.
- Click usage errors return Click's normal non-zero usage exit.

vBook bundle behavior:

- Exit `0`: transcription completed and manifest status is `done`.
- Exit `1`: transcription failed; vtext writes `manifest.json` with status
  `failed` when the output directory can be created.
- Refine failure does not change the exit code to `1`; it is recorded in
  `errors[]` with stage `refine`. vtext still writes `transcript.clean.txt` and
  `summary.md` fallback files derived from the raw transcript so vBook does not
  receive an exit-0 bundle with missing required outputs.

Stable error stages:

- `audio_extraction`
- `compression`
- `transcription`
- `refine`
- `output`

Stable error codes for the first pass:

- `server_connection_error`
- `queue_full`
- `server_error`
- `client_error`
- `refine_error`
- `unexpected_error`

## Batch Input And Output Structure

Current batch input:

```text
<input-root>/
|-- <series>/
|   +-- <lesson>.mp4
+-- other-media-files...
```

Current batch output without `--output`:

```text
<input-root>/
+-- text/
    +-- <series>/
        |-- <lesson>_raw.srt
        |-- <lesson>_clean.txt
        +-- <lesson>_summary.md
```

Current batch output with `--output <output-root>`:

```text
<output-root>/
+-- <series>/
    |-- <lesson>_raw.srt
    |-- <lesson>_clean.txt
    +-- <lesson>_summary.md
```

Batch manifest is not part of the first minimal implementation. vBook may call
vtext once per lesson using `--bundle vbook` and read each lesson manifest. A
batch-level manifest can be added after the per-lesson contract is stable.

## Service And Model Dependencies

Client-side dependencies:

- Python package `vtext`
- `ffmpeg` available on PATH
- `requests`, `click`, `zstandard`, `opencc-python-reimplemented`

Server-side dependencies:

- running `vtext-server`
- configured whisper.cpp binary
- configured whisper.cpp model
- reachable vtext server LLM relay for vBook bundle refine

Health command:

```powershell
python -m vtext_client --check-server --server "http://192.168.0.122:8000"
```

## Large-File And Service Limits

Known current limits:

- Client extracts the source media to 16 kHz mono WAV before upload.
- WAV files at or above 100 MB are zstd-compressed by the client.
- Server upload handling still reads the uploaded request body before writing the
  temporary WAV, so very large uploads are limited by server memory and
  `ServerConfig.max_file_size`.
- Server returns HTTP `413` for files above its configured maximum.
- Server returns HTTP `429` when the transcription queue is full.
- SSE waits up to the client request timeout; long lessons should be run against
  a stable server.

## Docs Layout Adoption

vtext has adopted a lightweight numbered docs layout for integration-relevant
material:

```text
docs/
|-- 00_project/
|-- 20_architecture/
|-- 40_development/
|-- 60_operations/
|-- 70_progress/
+-- 90_reference/
```

The vBook response remains in this reference layer, while day-to-day invocation
instructions live in `docs/60_operations/vbook-text-integration.md` and the
long-lived artifact contract lives in `docs/20_architecture/output-contracts.md`.

The first priority remains contract clarity, not cosmetic reorganization.

## Minimal Code Change Plan

1. Add an explicit `--bundle vbook` CLI option for single-video calls.
2. Require `--output <lesson-output-dir>` for `--bundle vbook`.
3. Write raw transcript artifacts using stable names:
   - `transcript.raw.txt`
   - `transcript.raw.srt` when `--format srt`
4. Write refine artifacts using stable names:
   - `transcript.clean.txt`
   - `summary.md`
5. Write `manifest.json` for success, refine-warning, and transcription-failure
   cases.
6. Keep legacy CLI and batch behavior unchanged.
7. Add focused tests for bundle success and failed transcription manifest output.

## Open Questions For vBook

- Should vBook pass `course`, `series`, and `lesson_title` explicitly, or is
  path inference acceptable for the first fixture?
- Does vBook need batch-level manifest support before preview generation, or is
  one call per lesson acceptable for the first integration pass?
- Should vBook surface fallback refine quality in operator dashboards, or is
  reading `manifest.json` `errors[]` sufficient for the first production pass?
