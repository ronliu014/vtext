# vtext Status

Last updated: 2026-08-14

## Current State

- The reviewed qwen-general OpenAPI 1.1.0 compatibility implementation is
  committed as `886b5b4`, deployed on production `:8000`, and verified through
  local/LAN health plus a successful end-to-end relay smoke.
- qwen-general 1.2.0 raises the pre-header read inactivity boundary from 300 to
  600 seconds. The cold/warm service qualification and the bounded two-job
  vBook canary both passed; the canary is formally `qualifying`.
- The qualifying canary does not authorize scheduler resume, publication,
  delivery, Vault writes, Wave 069 reruns, or general production recovery.
- vtext provides client/server audio and video transcription.
- The production request path is vBook/Windows CLI -> Linux vtext service at
  192.168.0.122:8000 -> qwen-general at vision.lingrengame.com:7866.
- The LLM refine baseline is explicitly pinned to qwen3.6:latest.
- Long refine input is split into bounded correction and structure chunks.
  Generic refine uses a 12,000-character cap accepted by vision; the published
  vBook production/recovery contract keeps its conservative 6,000-character cap.
- Relay jobs expose qwen-general OpenAPI 1.1.0 in health and preserve X-Request-ID,
  upstream HTTP status, error code, error source, and
  latency through status and SSE responses.
- The relay rejects requests above the gateway's 2 MiB body limit before queueing.
- Local Windows development should use the Anaconda App environment via
  D:\anaconda3\envs\App\python.exe.

## vBook Integration

- vBook calls vtext only through stable CLI, HTTP API, and artifact contracts.
- The vBook bundle keeps schema version 1 and complete fallback files on refine
  failure. Manifest errors and fallback file content make degradation explicit.
- A partial, empty, malformed, or prematurely terminated LLM response cannot be
  published as a successful refine result.
- Batch-level vBook manifests are not implemented yet; vBook can call vtext once
  per lesson.

## Known Limits

- The vision-managed gateway retains a 300-second write timeout and now has a
  600-second pre-header read timeout. The deployed vtext 900-second caller
  timeout cannot extend either gateway-owned boundary.
- Server upload handling still reads the request body before writing temporary
  audio, so very large uploads are constrained by configured max size and memory.
- The default/base Python environment may not include opencc; use the App
  environment for Traditional-to-Simplified conversion tests.
