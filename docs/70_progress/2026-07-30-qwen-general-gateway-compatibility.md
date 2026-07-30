# qwen-general Gateway Compatibility

Date: 2026-07-30
Status: implemented and validated; production deployment of current code pending

## Decision

- Keep the production path vBook/Windows CLI -> Linux vtext ->
  vision.lingrengame.com:7866.
- Pin the vtext refine baseline to qwen3.6:latest.
- Keep vtext upstream requests non-streaming and preserve the deployed 900-second
  caller timeout. The gateway still owns its 300-second read/write inactivity timeout.
- Use a vtext-owned 12,000-character maximum for refine chunks. vision confirmed
  this is acceptable when the final JSON request body stays at or below 2 MiB;
  the chunk size remains a vtext policy, not a qwen-general requirement.

## Compatibility Work

- Added X-Request-ID propagation from the vtext client through the relay and
  qwen-general.
- Added relay metadata for upstream HTTP status, error code, error source, and latency.
- Added a pre-queue 2 MiB body limit using the same JSON serialization shape
  sent by requests.
- Reject 413, 503, timeout, transport failure, malformed JSON, missing done=true, empty content,
  invalid SSE JSON, and prematurely terminated SSE as explicit failures.
- Return a complete refine tuple only after all correction and structure chunks
  succeed. Existing vBook schema-v1 raw-derived fallback remains explicit in
  manifest errors and file content.

## Verification

- Post-contract live OpenAPI refresh: `http://vision.lingrengame.com:7866/openapi.json`
  reports Qwen General API version 1.1.0 with ChatRequest/ChatResponse,
  X-Request-ID, raw-body limit, gateway/Ollama error, streaming completion,
  and read/write inactivity timeout contracts.
- Current working-tree relay validation used a temporary non-production vtext
  service on `127.0.0.1:8011` because restarting production `:8000` with a
  dirty tree was intentionally avoided. Health exposed `contract_version=1.1.0`,
  `qwen3.6:latest`, non-streaming mode, 900-second caller timeout, a 2 MiB
  request guard, and empty queues before and after validation.
- Temporary relay short chat: submission HTTP 201; terminal SSE done; request ID
  preserved end to end; upstream HTTP 200; upstream latency 12.247 seconds.
- Temporary representative refine validation: 12,000 input characters,
  conservative options `num_ctx=32768` and `num_predict=1024`; correction
  request measured 75,147 encoded bytes and completed with HTTP 200 in 29.1
  seconds; structure request measured 2,048 encoded bytes and completed with
  HTTP 200 in 12.0 seconds; combined client refine time was 41.279 seconds.
- Focused gateway compatibility matrix: 47 passed.
- Full repository suite: 257 passed.
- Ruff passed for the changed runtime modules and focused compatibility tests.
- Production `:8000` has not been restarted with the final contract-binding
  working tree and does not yet expose `contract_version=1.1.0`.
- The company-managed vision hostname was adopted and a post-clarification
  refresh of `http://vision.lingrengame.com:7866/openapi.json` confirmed
  the live Qwen General API 1.1.0 contract Current service URLs use the hostname rather
  than the former numeric host address.
- The deployed service was restarted with the domain endpoint. A post-restart
  relay chat completed with HTTP 200, a two-character result, end-to-end
  request-ID preservation, and 52.803 seconds upstream latency; both queues
  returned to zero.
- Direct qwen-general short chat: HTTP 200, X-Request-ID echoed, non-empty done
  response, 13.509 seconds cold and 1.183 seconds warm.
- vtext relay short chat: submission HTTP 201; terminal SSE done; upstream HTTP
  200; request ID preserved end to end; 1.228 seconds upstream latency.
- Live oversized gateway request: HTTP 413 in 0.036 seconds,
  `application/json`, `error=request_too_large`, and request ID echoed.
- Live oversized vtext relay request: locally rejected before queueing with
  HTTP 413 in 0.043 seconds; measured 2,097,259 bytes against the configured
  2,097,152-byte guard. The LLM queue remained empty.
- Synthetic multi-chunk refine: 570 input characters split into three 220-char
  chunks; all three correction and three structure calls returned HTTP 200 in
  43.129 seconds total. Per-call latency was 11.1, 2.8, 10.0, 5.9, 5.8, and
  6.1 seconds, with a distinct correlated request ID for each call.

## Remaining Work

- Create the deliberate vtext commit after final review and verification.
- Restart production `:8000` only with explicit user authorization, then verify
  health and run a short production relay smoke test.
- The validation response was delivered to vision through vsync remote `main`
  in commit `2d7d795`.
