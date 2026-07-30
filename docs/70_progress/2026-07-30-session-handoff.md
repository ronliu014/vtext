# Session Handoff: qwen-general Compatibility

Date: 2026-07-30
Source branch: `main`
Implementation commit: `886b5b4`
Working tree: clean after implementation commit; production deployment complete

## Objective

Complete the vtext compatibility work for the vision-owned qwen-general
gateway, preserve the confirmed contract, and hand off the reviewed production
state.

## Production Boundary

The production request path is fixed:

```text
vBook on Windows 192.168.5.1
  -> local vtext CLI
  -> vtext server / LLM relay at 192.168.0.122:8000
  -> qwen-general at vision.lingrengame.com:7866
```

The Windows client and vBook must not call the GPU gateway directly. Keep
`sync/` for intra-vtext Windows/Linux coordination and use `vsync` for
cross-project communication with vision and vBook.

## Implemented In Commit `886b5b4`

- Migrated the vision-owned production endpoint from the numeric host to
  `http://vision.lingrengame.com:7866`.
- Pinned the refine baseline to `qwen3.6:latest`.
- Preserved non-streaming upstream requests and the deployed 900-second vtext
  caller timeout. The gateway still owns a separate 300-second read/write
  inactivity timeout.
- Added end-to-end `X-Request-ID` propagation and relay metadata for upstream
  status, error code, error source, and latency.
- Added a pre-queue 2 MiB JSON request-size guard.
- Hardened HTTP and SSE handling for 413, 503, timeout, transport failure,
  malformed JSON, missing done=true, empty content, invalid SSE JSON, and premature SSE EOF.
- Made multi-chunk refine atomic: correction and structure output is published
  only after every chunk succeeds. Existing vBook schema-v1 fallback remains
  explicit in the manifest and artifact content.
- Added focused client, server, and integration compatibility tests and updated
  architecture, operations, status, and vBook integration documentation.

The detailed implementation and evidence snapshot is in
`docs/70_progress/2026-07-30-qwen-general-gateway-compatibility.md`.

## Verification And Deployment Evidence

- Full repository suite: `257 passed` after the final contract review.
- Focused gateway compatibility matrix: `47 passed`.
- Ruff passed for the new compatibility tests and changed runtime modules.
  Four unused-import reports in two legacy config test modules were pre-existing.
- Production `:8000` now runs the final contract-binding implementation.
  Local and LAN health report `contract_version=1.1.0`, `qwen3.6:latest`,
  non-streaming mode, a 900-second caller timeout, a 2 MiB request guard, and
  empty ASR/LLM queues.
- Post-deploy relay smoke `vtext-prod-9b53670df111` completed with submission
  HTTP 201, terminal SSE done, upstream HTTP 200, preserved request ID, and
  12.271 seconds upstream latency.
- Direct qwen-general and vtext relay smoke requests returned HTTP 200 with
  correlated request IDs.
- Live oversized requests were rejected with HTTP 413 before relay queueing.
- A synthetic three-chunk refine completed all six upstream calls successfully.

These checks were completed before this handoff. Re-run the relevant focused
tests after any contract-driven code change; do not treat the synthetic chunk
smoke as proof that a 12,000-character chunk fits inside the gateway deadline.

## External Coordination

The company-approved private coordination remote is:

```text
https://github.com/ronliu014/vsync.git
```

The qwen-general contract clarification request was committed as `e5dc6a7` and
is present on remote `main` through merge commit `866bb60`. It asks vision to
clarify `/api/chat` request and response schemas, request-ID behavior, body-size
measurement, timeout and error mapping, streaming completion, and the supported
long-refine budget.

At handoff time, the message has been pushed but vision has not been confirmed
to have pulled or replied. `vsync/v1` is a Git mailbox, so a push is delivery to
the shared remote, not proof that the recipient has fetched it.

CCB is retired and must not be used for coordination. The local
`@seemseam/ccb` npm package, wrappers, cache/state, CCB-only skills, projections,
and `agentroles.ccb_self` role were removed and verified absent. Use `vsync` for
durable cross-project messages and current Codex task tools only when task
coordination is explicitly needed.

## Remaining Decisions

1. Decide whether to push the local implementation and deployment-evidence
   commits to `origin/main`.
2. Run a Windows/vBook end-to-end lesson against the deployed relay when a
   consumer fixture is available.

## Post-Handoff Update

After this handoff, vision replied through vsync with
`2026-07-30-vision-vtext-qwen-general-openapi-contract-clarification-response.md`.
The reply confirms qwen-general OpenAPI 1.1.0, `done=true` success semantics,
2 MiB raw HTTP body limits, gateway-vs-Ollama error mapping, X-Request-ID
normalization, streaming completion rules, a 300-second read/write inactivity
timeout, and a conservative qwen3.6 refine profile of `stream=false`,
`think=false`, `num_ctx=32768`, and `num_predict=1024`.

The confirmed contract has now been bound in code and tests. Focused tests,
the full suite, a temporary current-code Linux relay smoke, and a representative
12,000-character refine run passed. The validation response was pushed to the
vsync remote in commit `2d7d795`. The reviewed implementation was committed as
`886b5b4`, deployed to production `:8000`, and verified through local/LAN
health and a successful relay smoke.

## Repository State

The reviewed runtime, tests, and documentation are committed in `886b5b4`.
The key runtime files are:

```text
vtext_client/api.py
vtext_client/config.py
vtext_client/refine.py
vtext_server/app.py
vtext_server/config.py
vtext_server/llm_client.py
vtext_server/llm_queue.py
vtext_server/llm_worker.py
```

New compatibility files include:

```text
docs/70_progress/2026-07-30-qwen-general-gateway-compatibility.md
tests/test_client/test_gateway_compat.py
tests/test_integration/test_gateway_contract.py
tests/test_server/test_llm_client.py
```

At completion, local `main` is clean with the implementation and
deployment-evidence commits ahead of `origin/main`.

## New Session Start

Begin with:

```sh
sed -n '1,260p' docs/70_progress/2026-07-30-session-handoff.md
sed -n '1,260p' docs/70_progress/2026-07-30-qwen-general-gateway-compatibility.md
git status -sb
git diff --stat
```

The vsync inbox now contains the vision contract response. Continue by applying
the confirmed OpenAPI 1.1.0 contract, rerunning focused tests, and preparing the
deliberate vtext commit after review.
