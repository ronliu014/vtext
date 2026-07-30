# 2026-07-30 Session Handoff

Date: 2026-07-30
Branch: `main`
Scope: wave 009 recovery, qwen-general compatibility, and production deployment

## Current State

- The remote Windows-side work in `ad22455` adds 6,000-character vBook
  chunking and `--refine-only --bundle vbook` recovery with manifest audit
  history.
- The Linux-side implementation in `886b5b4` binds the relay to
  qwen-general OpenAPI 1.1.0, qwen3.6, request correlation, structured errors,
  a 2 MiB body guard, and validated completion semantics.
- Production `192.168.0.122:8000` runs the server implementation from
  `886b5b4`; local and LAN health expose `contract_version=1.1.0`.
- Deployment evidence is recorded in `fd434c1`.
- The cross-project validation response is on the vsync remote in `2d7d795`.

## Fixed Ownership And Request Path

```text
Windows 192.168.5.1, owner wcodex
vBook -> local vtext CLI
          |
          | HTTP / SSE
          v
Linux 192.168.0.122:8000, owner lcodex
vtext server / LLM relay
          |
          | Ollama-compatible HTTP API
          v
vision.lingrengame.com:7866
qwen-general gateway
```

Durable boundaries:

- vBook may use only the stable vtext CLI, HTTP API, and artifact contracts.
- Windows and vBook must not connect directly to the GPU gateway or raw Ollama.
- `sync/` is the internal wcodex/lcodex Git mailbox.
- `vsync` is the cross-project mailbox for vtext, vBook, and vision.
- Linux service configuration, logs, restarts, and upstream model calls belong
  to lcodex.

## Relevant History

| Commit | Result |
| --- | --- |
| `7b6687b` | Documented Windows/Linux ownership boundaries |
| `e67250d` | Documented the fixed production request path |
| `e4b5df5` | Enforced the vBook server-relay and fallback contract |
| `ac289ce` | Sent the wave 009 Linux investigation request through `sync/` |
| `5f290c6` | Integrated the wave 009 Linux diagnosis |
| `ad22455` | Added chunked vBook refine and refine-only bundle recovery |
| `886b5b4` | Added qwen-general OpenAPI 1.1.0 compatibility |
| `fd434c1` | Recorded production deployment evidence |

## Wave 009 Diagnosis

Failed production item:

```text
run_id: R20260720-vtext-wave-009
task_id: 001-ec54d159110f
lesson: 量化模式/主升浪战法/前途无量模式—跟踪高控盘主力的利器
```

Both failed attempts reached the Linux vtext server and GPU service. ASR
completed twice with 1,623 segments. The two full-transcript LLM jobs timed out
after approximately 900 seconds. Worker health, queue health, short relay calls,
and a 45,500-character bounded-output probe were healthy.

The root cause was the long-output request shape, not Windows localhost,
networking, dead workers, ASR failure, or incorrect GPU ownership.

Internal evidence:

```text
sync/s2c/000012-20260722T030044Z-a9c13f2b.json
in_reply_to: d043efbf
```

## Wave 009 Controlled Recovery

The operator explicitly authorized a targeted recovery on 2026-07-22. The
existing raw transcript was processed through the server relay in three
6,000-character chunks, for six correction/structure calls. ASR was not rerun.

Artifact path:

```text
E:/projects/my_app/vbook/outputs/production-artifacts/vtext-wave-009/001-ec54d159110f
```

Validated result:

```text
manifest.status=done
manifest.errors=[]
outputs.raw_txt=true
outputs.raw_srt=true
outputs.clean_txt=true
outputs.summary_md=true
recovery.mode=chunked_refine_only
recovery.source=transcript.raw.txt
recovery.chunk_chars=6000
recovery.previous_errors count=1
recovery.recovered_at=2026-07-22T03:41:11Z
```

The raw transcript SHA-256 remained unchanged:

```text
430A75970CB943B2AD4C6F81CC8CE986A5A7CF1C8A59F9F168D9084EAE18E702
```

Do not rerun wave 009 ASR/refine, delete `control/pause.request`, or rewrite
the two failed vBook attempts without a new explicit operator decision. vBook
owns artifact reconciliation and pause resolution.

The recovery result is recorded in vsync commits `63a933f` and `c85ba19`.

## Integrated Refine Policies

- Generic refine uses `DEFAULT_REFINE_CHUNK_CHARS=12000`. vision confirmed
  this vtext-owned policy is acceptable when the final encoded request body is
  at or below 2 MiB.
- vBook production and refine-only recovery retain the published conservative
  `REFINE_CHUNK_CHARS=6000` contract from `ad22455`.
- Both paths use qwen3.6 options `temperature=0.4`, `num_ctx=32768`, and
  `num_predict=1024`.
- vBook always uses the Linux server relay. Direct mode and disabled refine are
  rejected for vBook bundles.
- A complete refine result is returned only after all bounded correction and
  structure calls succeed.
- Refine-only recovery preserves previous refine errors under
  `manifest.recovery.previous_errors` and never rewrites raw transcripts.

## qwen-general Contract

- OpenAPI version: `1.1.0`.
- Upstream path: `http://vision.lingrengame.com:7866/api/chat`.
- Success requires HTTP 200, non-empty assistant content, and `done=true`.
- Relay requests use `stream=false` and `think=false`.
- Raw request-body limit: exactly 2,097,152 bytes.
- Gateway timeout: 300-second read/write inactivity window.
- vtext caller timeout: 900 seconds.
- Request IDs are opaque 1-128 character values; invalid or missing values are
  replaced with 32-character lowercase hexadecimal UUIDs.
- Gateway errors and Ollama errors remain distinguishable in relay metadata.

## Verification And Production Evidence

- Post-merge focused compatibility matrix: `53 passed`.
- Post-merge client/gateway/LLM integration matrix: `140 passed`.
- Post-merge full Linux suite: `266 passed`.
- Post-merge changed-file Ruff and `git diff --check`: passed.
- Temporary current-code 12,000-character refine: correction request 75,147
  encoded bytes, 29.1 seconds; structure request 2,048 bytes, 12.0 seconds.
- Production health on both `127.0.0.1:8000` and
  `192.168.0.122:8000`: HTTP 200, contract 1.1.0, qwen3.6, empty queues.
- Production smoke `vtext-prod-9b53670df111`: submission HTTP 201, terminal
  SSE done, upstream HTTP 200, request ID preserved, 12.271 seconds upstream
  latency, queues zero afterward.

The first deployment restart exposed an older vtext process detached from the
current systemd unit cgroup and still holding `:8000`. Its queues were empty.
It exited cleanly on SIGTERM; the port was verified free; the unit then started
under its expected control group.

Post-merge acceptance completed successfully across the full Linux suite,
focused gateway tests, client recovery tests, changed-file Ruff, and
`git diff --check`.

## External Coordination

Canonical qwen-general messages:

```text
mailbox/messages/2026-07-30-vision-vtext-qwen-general-openapi-contract-clarification-response.md
mailbox/messages/2026-07-30-vtext-vision-qwen-general-contract-validation-response.md
```

The company-approved private coordination remote is:

```text
https://github.com/ronliu014/vsync.git
```

Do not use CCB. Do not conflate `sync/` and `vsync`.

## Remaining Ownership

- vBook owns reconciliation of the recovered wave 009 artifact and removal of
  its pause after validation.
- A Windows/vBook end-to-end lesson against the deployed relay remains useful
  when a consumer fixture is available.
- A separate post-deployment vsync message is optional; the contract validation
  response is already delivered.

## Next Session Checklist

1. Read `AGENTS.md`, this handoff, and the qwen-general compatibility report.
2. Run `git status --short --branch` before making changes.
3. Preserve the fixed Windows -> Linux vtext -> vision request path.
4. Do not rerun wave 009 or mutate vBook history without explicit approval.
5. Use the Windows Anaconda `App` interpreter for Windows-side tests.
6. Use `/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3` on Linux.
