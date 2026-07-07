# vtext Overview

`vtext` is a client-server audio/video transcription tool built around
`ffmpeg`, `whisper.cpp`, and a lightweight Python CLI.

The client owns local media preparation: it extracts 16 kHz mono WAV audio,
optionally compresses large uploads with zstd, submits transcription jobs, and
writes text artifacts. The server owns the heavy work: FastAPI endpoints, job
queueing, multiprocessing workers, whisper.cpp subprocess execution, model
management, and optional LLM relay for text refinement.

## Project Role

vtext can run as a standalone transcription tool, and it also acts as the text
processing module for sibling project vBook. For vBook integration, vtext exposes
stable CLI/API/artifact contracts; vBook must not import or vendor vtext
internal Python modules.

## Primary Packages

- `vtext_client/` - CLI, HTTP client, ffmpeg audio extraction, batch processing,
  output writing, and vBook bundle generation.
- `vtext_server/` - FastAPI app, transcription queue, worker processes,
  whisper.cpp integration, model handling, and LLM relay queue.
- `vtext_common/` - shared dataclasses, job status enum, and output formatting
  helpers for `txt`, `srt`, and `vtt`.

## Important Boundaries

- The client should stay lightweight and must not import server-only FastAPI or
  worker dependencies.
- ffmpeg runs on the client; the server receives WAV or zstd-compressed WAV.
- whisper.cpp is called as a subprocess, not through a Python binding.
- `vtext_common.types.JobStatus` is the shared status enum.
- Cross-project coordination happens through docs, CLI/API, and artifacts.

