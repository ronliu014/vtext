# vtext Status

Last updated: 2026-07-30

## Current State

- After vision confirmed qwen-general OpenAPI 1.1.0, local compatibility tests
  and a non-production live relay/representative refine validation pass with
  the conservative qwen3.6 profile. Production `:8000` has not been restarted
  with the dirty working tree.
- vtext provides client/server audio and video transcription.
- The production request path is vBook/Windows CLI -> Linux vtext service at
  192.168.0.122:8000 -> qwen-general at vision.lingrengame.com:7866.
- The LLM refine baseline is explicitly pinned to qwen3.6:latest.
- Long refine input is split into bounded correction and structure chunks. The
  current 12,000-character cap is a vtext policy that vision confirmed acceptable
  when the final encoded JSON request body stays at or below 2 MiB.
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

- The vision-managed gateway has a 300-second read/write inactivity timeout.
  The deployed vtext 900-second caller timeout cannot extend that inactivity
  window.
- The qwen-general OpenAPI 1.1.0 boundary has been validated with a temporary
  current-code service. Production `:8000` still needs a reviewed deployment
  and post-restart smoke test.
- Server upload handling still reads the request body before writing temporary
  audio, so very large uploads are constrained by configured max size and memory.
- The default/base Python environment may not include opencc; use the App
  environment for Traditional-to-Simplified conversion tests.
