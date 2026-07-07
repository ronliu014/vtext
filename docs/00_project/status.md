# vtext Status

Last updated: 2026-07-07

## Current State

- vtext provides client/server audio and video transcription.
- The client can generate raw transcripts and optional LLM-refined clean text
  plus summary artifacts.
- The server exposes transcription, job status, SSE progress, health, model, and
  LLM relay endpoints.
- CodeGraph has been initialized for this repository.
- Local Windows development should use the Anaconda `App` environment via
  `D:\anaconda3\envs\App\python.exe`.

## vBook Integration

- vtext has accepted the vBook text integration boundary: vBook calls vtext
  through stable CLI/API/artifact contracts, not internal imports.
- `--bundle vbook` is implemented for single-video per-lesson output.
- vBook bundle output includes `manifest.json`, `transcript.raw.txt`, optional
  `transcript.raw.srt`, and refine artifacts when available.
- Batch-level vBook manifests are not implemented yet; vBook can call vtext once
  per lesson for the first integration pass.

## Known Limits

- Server upload handling still reads the request body before writing temporary
  audio, so very large uploads are constrained by configured max size and server
  memory.
- Refine depends on either direct Ollama access or the vtext server LLM relay.
- The default/base Python environment may not include `opencc`; use the `App`
  environment for tests involving Traditional-to-Simplified conversion.

