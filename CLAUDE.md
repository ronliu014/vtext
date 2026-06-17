# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`vtext` is a client-server audio/video transcription tool built on whisper.cpp and ffmpeg. The server handles heavy transcription work; the client is a lightweight CLI that communicates with the server over HTTP.

## Environment

- Python: `/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3` (use this explicitly; the default pyenv shim points to 3.13.12 which has a broken pip)
- whisper.cpp: `/mnt/data/projects/whisper.cpp/build/bin/whisper-cli`
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

## Deployment (systemd user service)

The server runs as a systemd user service on this machine:

```sh
# Service file: ~/.config/systemd/user/vtext.service
systemctl --user status vtext
systemctl --user restart vtext
journalctl --user -u vtext -f
```

Service is enabled with `loginctl enable-linger ubuntu` so it survives logout.

## whisper.cpp

Binary lives at `/mnt/data/projects/whisper.cpp/`. If recompilation is needed (e.g. after moving the directory):

```sh
cd /mnt/data/projects/whisper.cpp
rm -rf build
cmake -B build -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON
cmake --build build --target whisper-cli -j$(nproc)
```

The `RPATH_USE_ORIGIN` flag is required so the binary finds `libwhisper.so` relative to its own location without needing `LD_LIBRARY_PATH`.

## Architecture

Three Python packages live in one repo:

- **`vtext_server/`** — FastAPI app. Wraps whisper.cpp (subprocess) and ffmpeg for audio extraction. Handles model download/management. Entry point: `vtext_server.__main__:main`.
- **`vtext_client/`** — CLI (click) + HTTP client (requests). No heavy deps. Entry point: `vtext_client.__main__:main`.
- **`vtext_common/`** — Shared types and output format helpers (txt/srt/vtt). Imported by both packages.

### Key design rules

- The client **only** uses `requests` and `click` — never import server-side deps in client code.
- **ffmpeg runs on the client** (`vtext_client/audio.py`) to extract 16 kHz mono WAV before upload. The server only ever receives WAV files.
- whisper.cpp is called as a **subprocess** inside `vtext_server/transcriber.py`, not via a Python binding. Output is parsed from `--output-json`.
- Files ≥ 100 MB are compressed with zstd level 3 on the client before upload; `encoding=zstd` is passed as a form field so the server knows to decompress.
- `vtext_common/types.py` defines the shared `JobStatus` enum used by both server queue and client.

### Async job flow

1. `POST /transcribe` → decompresses if needed, enqueues, returns `{job_id, status, position}` (HTTP 201). Returns HTTP 429 with queue stats if full.
2. `GET /jobs/{job_id}/stream` → SSE stream. Events: `queued` (position), `processing` (progress 0–100), `done` (result JSON), `error` (message).
3. `GET /jobs/{job_id}` → polling alternative; returns current status snapshot.

Server uses `multiprocessing` workers (not threads) — configured by `--workers`. Worker count and queue size are in `ServerConfig`.

### REST API (server exposes)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/transcribe` | Upload WAV, enqueue job, return job_id |
| `GET`  | `/jobs/{id}/stream` | SSE progress stream |
| `GET`  | `/jobs/{id}` | Job status snapshot |
| `GET`  | `/health` | Server/queue/worker status |
| `GET`  | `/models` | List available/cached models |
| `POST` | `/models/download` | Download a named model |

`POST /transcribe` form fields: `file` (binary), `encoding` (`zstd` or omit), `language` (optional), `format` (`txt`/`srt`/`vtt`), `model` (optional name override).

### Configuration priority

Both client and server resolve config in this order: CLI args → environment variables → `~/.config/vtext/{client,server}.toml` → defaults.

Key env vars:
- `VTEXT_SERVER_URL` — client server URL (default: `http://127.0.0.1:8000`)
- `WHISPER_CPP_BIN` — path to whisper.cpp binary
- `WHISPER_CPP_MODEL` — path to model file

### Error hierarchy

- `vtext_client/errors.py`: `VtextClientError` → `ServerConnectionError`, `ServerError`, `TimeoutError`
- `vtext_server/errors.py`: `VtextServerError` → `DependencyError`, `TranscriptionError`, `ModelNotFoundError`

### Resource limits (server defaults)

- Max file size: 500 MB
- Max concurrent requests: 4
- Request timeout: 300 s
