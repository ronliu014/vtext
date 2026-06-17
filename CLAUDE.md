# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`vtext` is a client-server audio/video transcription tool built on whisper.cpp and ffmpeg. The server handles heavy transcription work; the client is a lightweight CLI that communicates with the server over HTTP.

## Commands

```sh
# Install client only
pip install -e .

# Install with server dependencies
pip install -e ".[server]"

# Install with dev dependencies
pip install -e ".[full,dev]"

# Run tests
pytest

# Run a single test file
pytest tests/test_server/test_app.py

# Run with coverage
pytest --cov

# Lint / format
ruff check .
black .

# Start the server (dev)
vtext-server --model tiny

# Use the client
vtext video.mp4
```

## Architecture

Three Python packages live in one repo:

- **`vtext_server/`** — FastAPI app. Wraps whisper.cpp (subprocess) and ffmpeg for audio extraction. Handles model download/management. Entry point: `vtext_server.__main__:main`.
- **`vtext_client/`** — CLI (click) + HTTP client (requests). No heavy deps. Entry point: `vtext_client.__main__:main`.
- **`vtext_common/`** — Shared types and output format helpers (txt/srt/vtt). Imported by both packages.

### Key design rules

- The client **only** uses `requests` and `click` — never import server-side deps in client code.
- whisper.cpp is called as a **subprocess** inside `vtext_server/transcriber.py`, not via a Python binding.
- ffmpeg audio extraction happens in `vtext_server/audio.py` before passing audio to whisper.cpp.
- `vtext_common/types.py` defines the shared data model for transcription results (segments with start/end/text).

### REST API (server exposes)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/transcribe` | Upload file, returns transcript with segments |
| `GET` | `/health` | Server status and loaded model info |
| `GET` | `/models` | List available/cached models |
| `POST` | `/models/download` | Download a model by name |

`POST /transcribe` accepts `multipart/form-data` with fields: `file`, `language` (optional), `format` (txt/srt/vtt), `model` (optional override).

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
