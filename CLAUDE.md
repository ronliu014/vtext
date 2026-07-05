# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`vtext` is a client-server audio/video transcription tool built on whisper.cpp and ffmpeg. The server handles heavy transcription work; the client is a lightweight CLI that communicates with the server over HTTP.

## Environment

- Python: `/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3` — use this explicitly; the default pyenv shim points to 3.13.12 which has a broken pip
- whisper.cpp binary: `/mnt/data/projects/whisper.cpp/build/bin/whisper-cli`
- Server config: `~/.config/vtext/server.toml`

## Commands

```sh
# Install with dev dependencies (use the 3.13.2 pip directly)
/mnt/data/profile/.pyenv/versions/3.13.2/bin/pip3 install -e ".[full,dev]"

# Run tests
/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3 -m pytest

# Run a single test file
/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3 -m pytest tests/test_server/test_app.py

# Run with coverage
/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3 -m pytest --cov

# Lint / format
ruff check .
black .

# Start the server (dev)
/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3 -m vtext_server

# Use the client
/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3 -m vtext_client video.mp4
```

## whisper.cpp recompilation

If the binary needs rebuilding (e.g. after moving the directory), the `RPATH_USE_ORIGIN` flag is mandatory — without it the binary cannot find `libwhisper.so` at runtime:

```sh
cd /mnt/data/projects/whisper.cpp
rm -rf build
cmake -B build -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON
cmake --build build --target whisper-cli -j$(nproc)
```

## Architecture

Three Python packages in one repo:

- **`vtext_server/`** — FastAPI app. Wraps whisper.cpp (subprocess) and ffmpeg. Entry point: `vtext_server.__main__:main`.
- **`vtext_client/`** — CLI (click) + HTTP client (requests). No heavy deps. Entry point: `vtext_client.__main__:main`.
- **`vtext_common/`** — Shared types and output format helpers (txt/srt/vtt).

### Key design rules

- The client **only** uses `requests` and `click` — never import server-side deps in client code.
- **ffmpeg runs on the client** (`vtext_client/audio.py`) to extract 16 kHz mono WAV before upload. The server only ever receives WAV files.
- whisper.cpp is called as a **subprocess** in `vtext_server/transcriber.py`, not via a Python binding. Output is parsed from `--output-json`.
- Files ≥ 100 MB are compressed with zstd level 3 on the client; `encoding=zstd` form field signals the server to decompress.
- `vtext_common/types.py` defines the shared `JobStatus` enum — do not redefine it in server or client code.

### Async job flow

1. `POST /transcribe` → enqueues, returns `{job_id, status, position}` (HTTP 201). Returns HTTP 429 if queue full.
2. `GET /jobs/{job_id}/stream` → SSE stream with events: `queued`, `processing`, `done`, `error`.
3. `GET /jobs/{job_id}` → polling alternative.

Server uses `multiprocessing` workers (not threads).
