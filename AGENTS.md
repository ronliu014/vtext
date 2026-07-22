# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

`vtext` is a client-server audio/video transcription tool built on whisper.cpp and ffmpeg. The server handles heavy transcription work; the client is a lightweight CLI that communicates with the server over HTTP.

## Deployment Topology and Communication Boundaries

Treat these locations, owners, and communication channels as durable project boundaries:

| Scope | Production location | Agent owner | Responsibility |
|-------|---------------------|-------------|----------------|
| vtext client / CLI | Windows `192.168.5.1` | `wcodex` | CLI execution, client-side ffmpeg/audio extraction, server invocation, and local artifacts |
| vtext server | Linux `192.168.0.122` | `lcodex` | Deployed transcription service, queues, runtime config, logs, restarts, and upstream model calls |
| Internal vtext coordination | This repository's `sync/` directory | `wcodex` ↔ `lcodex` | Git-transported `vtext-sync/1` operations and control messages between the Windows client side and Linux server side |

### Production Business Connectivity

The following is the fixed production request path. Arrows show the direction of business requests:

```text
Windows 192.168.5.1 (wcodex)
vBook -> vtext CLI
          |
          | HTTP / SSE
          v
192.168.0.122:8000 (lcodex)
Linux vtext server / LLM relay
          |
          | Ollama HTTP API
          v
192.168.0.33:7866
GPU Ollama
```

vBook invokes only the local Windows vtext CLI, and the CLI submits production requests only to `192.168.0.122:8000`. Only the Linux vtext server / LLM relay connects to `192.168.0.33:7866`. There is no production edge from vBook or the Windows vtext CLI directly to GPU Ollama.

Mandatory boundaries:

- `vBook` is an external consumer. It may use only the stable vtext CLI, HTTP API, and artifact contracts; it must never import or vendor vtext internals.
- `sync/` is the **intra-project** Git mailbox for `wcodex` and `lcodex`. Follow `sync/PROTOCOL.md`; do not use it as the cross-project mailbox or as a replacement for the HTTP/SSE transcription data plane.
- `vsync` is the **cross-project** Git mailbox for communication among vtext, vBook, vision, and other registered projects.
- Never conflate `sync` and `vsync`: use `sync/` for Windows ↔ Linux coordination inside vtext, and use `vsync` for project ↔ project coordination.
- Production GPU/Ollama connectivity is owned by the vtext server. Do not diagnose a Windows `localhost:11434` refusal as evidence that Windows should host Ollama, and do not reconfigure vBook or the Windows CLI to bypass `192.168.0.122` for production model calls.
- Local Windows code changes are not deployed until `lcodex` applies or pulls them on the Linux server and reports deployment evidence.

## Environment

- Local Windows development environment: use the Anaconda `App` environment.
  Prefer invoking the interpreter directly instead of bare `python` or
  `conda run`, because `conda run` can trip over Windows quoting/temp-file
  behavior in this shell:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m pytest
& 'D:\anaconda3\envs\App\python.exe' -m pytest tests/test_client
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client video.mp4
```

- The `App` environment includes `opencc`; `tests/test_client/test_refine.py`
  depends on it for Traditional-to-Simplified Chinese conversion. Running the
  same tests with the default/base Python may fail with unchanged text because
  `opencc` is missing.
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

## vsync Cross-Project Coordination

vText participates in `vsync/v1` as the text, manifest, and LLM-fusion support service for the v-series video-note processing cluster. Use vsync as the central mailbox for durable communication with `vbook` and `vision`; do not rely on chat history as the cross-project record.

Canonical protocol:

- `E:/projects/my_app/vsync/PROTOCOL.md`

Mailbox:

- inbox: `E:/projects/my_app/vsync/mailbox/inbox/vtext/README.md`
- outbox: `E:/projects/my_app/vsync/mailbox/outbox/vtext/README.md`
- messages: `E:/projects/my_app/vsync/mailbox/messages/`

When creating, replying to, querying, indexing, or auditing cross-project messages, use:

- `E:/projects/my_app/vsync/skills/cross-project-communication/SKILL.md`

Rules:

- Store canonical cross-project messages in `vsync/mailbox/messages/`.
- Index sent messages in `vsync/mailbox/outbox/vtext/README.md`.
- Check received messages in `vsync/mailbox/inbox/vtext/README.md`.
- Use `Protocol: vsync/v1` and `Mailbox-Path:` in new message envelopes.
- Do not write mailbox copies into `vbook` or `vision` repositories.
- Update vText docs only when a mailbox message changes durable vText-owned facts such as contracts, runbooks, operations, compatibility, defaults, latency, risk, or backlog.
- Keep videos, generated notes, extracted frames, large logs, and model artifacts out of vsync messages; link paths and summarize evidence instead.
