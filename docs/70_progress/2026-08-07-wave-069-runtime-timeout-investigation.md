# Wave 069 qwen-general Runtime Timeout Investigation

Date: 2026-08-07
Status: bounded diagnosis complete; vision runtime evidence required
Decision: `vision_evidence_required`

## Incident Result

Wave 069 ultimately completed after an automatic retry, but the run was
degraded. The first refine request reached the vtext LLM worker without a
meaningful local queue wait and then received an explicit qwen-general HTTP 504
`runtime_timeout` after about 300 seconds. A successful retry does not turn the
canary into a clean pass.

Correlated failure:

- vtext job: `5cfa2783`
- request ID: `852b6d8f9c7442d4b7edc11b20608af8`
- request size: 16,124 encoded bytes
- queued: `2026-08-07T06:38:46.273060Z`
- worker start: `2026-08-07T06:38:46.274441Z`
- queue wait: approximately 0.001 seconds
- worker error: `2026-08-07T06:43:46.644776Z`
- upstream result: HTTP 504, `runtime_timeout`, source `gateway`
- upstream elapsed: 300.4 seconds in the vtext log; 300.361 seconds in the
  Windows artifact

The next LLM job, `3cb8429c` / request ID
`86ba2b019700486d88e2cc29316e97b0`, entered the single-worker FIFO at
`06:39:39.191847Z`, started at `06:43:46.649461Z`, and completed with HTTP 200
at `06:48:23.995672Z`. Its queue wait was approximately 247.458 seconds and its
own upstream execution took 277.3 seconds. Concurrent CLI submissions are
accepted and serialized, but their long-tail latency is cumulative.

The retry correction used the same 16,124-byte request shape. Job `891654b6`,
request `f576d77f6f4647b98a4165a3334797ad`, waited approximately 147.275
seconds and then completed with HTTP 200 in 272.3 upstream seconds. Its
following structure call, `dba6eede` /
`7cf390c96a744af8b21000e4f710bae3`, completed with HTTP 200 in 247.3 seconds.
These successes bound the failure to upstream runtime behavior close to the
gateway limit; they do not explain why the first request crossed that limit.

## Effective Deployment

The event-time and current process are the same process:

- effective server code revision: `886b5b4`
- package: editable vtext 0.1.5 from `/mnt/data/projects/vtext`
- user systemd unit: `vtext.service`
- unit file: `/home/ubuntu/.config/systemd/user/vtext.service`
- main PID: `314620`; LLM worker PID: `314655`
- started: `2026-07-30T07:35:47Z`
- upstream: `http://vision.lingrengame.com:7866`
- model: `qwen3.6:latest`
- request mode: non-streaming, `think=false`
- vtext caller timeout: 900 seconds
- LLM workers: 1, strict FIFO
- LLM queue capacity: 16
- request guard: exactly 2,097,152 encoded bytes

No `vtext_server` file differs between deployed revision `886b5b4` and the
current repository line. The process has not restarted since deployment. The
post-incident health check returned HTTP 200 with both queues empty and no busy
workers.

Read-only qwen-general checks returned healthy, Ollama runtime 0.20.7.
`/api/ps` showed `qwen3.5:9b` loaded at check time. That proves only current
shared runtime/model state, not event-time residency or a model switch during
the failed request.

## Timeout Layers

The 900-second vtext value is the caller HTTP wait budget. qwen-general
independently enforces a 300-second gateway-to-Ollama read/write inactivity
window. With `stream=false`, a long generation can produce no response body
until the complete result is ready.

qwen-general returned an explicit HTTP 504 at its own boundary before vtext's
900-second budget expired. vtext correctly classified and propagated that
response. Raising the vtext timeout cannot extend the gateway or Ollama limit.

## Concurrency Decision

Two concurrent CLI jobs are functionally supported by admission into the
single-worker queue, but this workload is not compatible with a clean two-job
production canary latency envelope. One 277-second execution behind another
request already produced about 525 seconds from submission to completion.

Keep `llm_workers=1` until vision provides runtime-capacity evidence. Increasing
workers could increase GPU contention and model churn. Do not increase the
900-second caller timeout, create a vBook-only route, or allow direct GPU access.

## Vision Evidence Gap

vtext cannot access qwen-general or Ollama runtime logs. vision should inspect:

- primary request ID: `852b6d8f9c7442d4b7edc11b20608af8`
- exact window: `2026-08-07T06:38:46.274Z` through
  `2026-08-07T06:43:46.645Z`
- surrounding window: `2026-08-07T06:35:00Z` through
  `2026-08-07T06:50:00Z`
- successful comparison: `86ba2b019700486d88e2cc29316e97b0`
- successful retry: `f576d77f6f4647b98a4165a3334797ad`

The response needs gateway receive/connect/pool/read timestamps, the precise
timed-out operation, model load/residency or swap events, concurrent runtime
requests, prompt-eval and generation durations/counts, termination reason,
GPU pressure or OOM evidence, and any Ollama runtime error.

## Evidence Preservation

Original sanitized logs:

- `/home/ubuntu/.local/share/vtext/logs/vtext-server.log`
- `/home/ubuntu/.local/share/vtext/logs/vtext-server.log.2026-07-30.log`
- `journalctl --user -u vtext.service` for the UTC windows above

Snapshots excluded from Git:

- `/tmp/vtext-wave069-evidence/vtext-server.log.snapshot-20260807`
  SHA-256 `63ac861a67aa160b0a1463426d5f0d81d0c18986b41d7d29955e6268bd2befca`
- `/tmp/vtext-wave069-evidence/vtext-worker.log.snapshot-20260807`
  SHA-256 `9730b43902e7338cec8649da1c746c1e2670140f8800bd144b82453312355860`

## Bounded Acceptance Test

Do not rerun Wave 069. After vision returns evidence, run one operator-approved
two-job canary with the scheduler otherwise paused:

1. Use two fixed representative vBook lessons through
   `Windows -> 192.168.0.122:8000 -> qwen-general`, with the published
   6,000-character vBook cap and current qwen3.6 profile.
2. Capture every job ID, request ID, request size, queue time, worker start/end,
   upstream status/error, and upstream elapsed time.
3. Require every correction and structure call to succeed on its first attempt,
   manifests `status=done` with `errors=[]`, no fallback, 429/5xx, direct GPU
   access, or residual queue work.
4. Below 270 upstream seconds is a clean latency pass. From 270 to below 300 is
   completed but degraded headroom. At least 300 seconds or any timeout fails.
5. Any automatic retry makes the canary degraded even if final artifacts
   succeed.

No production restart or configuration change was made during this
investigation.
