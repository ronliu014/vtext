# 2026-07-30 Session Handoff

## Purpose

This document is the continuation point for the next vtext Windows-side Codex
session. It records the completed wave 009 incident work, the current production
state, repository boundaries, and the new action required by the 7866 gateway
deployment notice.

Read this document after `AGENTS.md`. Do not infer production topology or agent
ownership from older chat history.

## Fixed Ownership And Request Path

```text
Windows 192.168.5.1, owner wcodex
vBook -> vtext CLI
          |
          | HTTP / SSE
          v
192.168.0.122:8000, owner lcodex
Linux vtext server / LLM relay
          |
          | Ollama-compatible HTTP API
          v
192.168.0.33:7866, owner vision platform
qwen-general gateway -> loopback Ollama runtime
```

Durable boundaries:

- vBook may call only the stable vtext CLI/API/artifact contract. It must not
  import or vendor vtext internals.
- `vtext/sync/` is the internal wcodex/lcodex Git mailbox.
- `vsync` is the cross-project mailbox for vtext, vBook, and vision.
- Windows and vBook must not connect directly to the GPU host or hidden raw
  Ollama ports.
- Linux service changes, deployed configuration, logs, and restarts belong to
  lcodex.

## Completed vtext Changes

Published on vtext `main`:

| Commit | Result |
| --- | --- |
| `7b6687b` | Documented Windows/Linux ownership and communication boundaries |
| `e67250d` | Documented the fixed production request path |
| `e4b5df5` | Enforced the vBook server-relay contract and fallback outputs |
| `ac289ce` | Sent the wave 009 Linux investigation request through `sync/` |
| `5f290c6` | Integrated lcodex's wave 009 diagnosis |
| `ad22455` | Added chunked vBook refine and refine-only bundle recovery |

`ad22455` provides these stable behaviors:

- vBook refinement always uses the Linux server relay.
- `--refine-mode direct` and disabled refinement are rejected for normal vBook
  bundle production.
- transcripts over 6,000 characters are refined in sentence-bounded chunks;
- `--refine-only --bundle vbook` recovers an existing bundle without rerunning
  ASR;
- successful recovery clears active refine errors and preserves them under
  `manifest.recovery.previous_errors`;
- raw transcript artifacts are not rewritten by recovery.

Verification at publication time:

```text
tests/test_client: 100 passed
python -m compileall: passed
git diff --check: passed
```

The `App` environment did not have `ruff` or `black`, so those checks were not
run. Pytest may need a repository-local `--basetemp` because the system pytest
temporary directory has produced `PermissionError` on this Windows host.

## Wave 009 Diagnosis

Failed production item:

```text
run_id: R20260720-vtext-wave-009
task_id: 001-ec54d159110f
lesson: 量化模式/主升浪战法/前途无量模式—跟踪高控盘主力的利器
```

lcodex proved that both failed attempts reached the Linux vtext server and GPU
service. ASR completed twice with 1,623 segments. The two full-transcript LLM
jobs timed out after approximately 900 seconds. Worker health, queue health,
short relay calls, and a 45,500-character bounded-output probe were healthy.

The root cause was the long-output request shape, not Windows localhost, broken
networking, dead workers, ASR failure, or incorrect GPU ownership.

Internal evidence:

```text
sync/s2c/000012-20260722T030044Z-a9c13f2b.json
in_reply_to: d043efbf
```

## Wave 009 Controlled Recovery

The operator explicitly authorized a targeted recovery on 2026-07-22. wcodex
ran the existing raw transcript through the new chunked refine-only path:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  "E:\projects\my_app\vbook\outputs\production-artifacts\vtext-wave-009\001-ec54d159110f\transcript.raw.txt" `
  --server "http://192.168.0.122:8000" `
  --refine-mode server `
  --refine-only `
  --bundle vbook `
  --output "E:\projects\my_app\vbook\outputs\production-artifacts\vtext-wave-009\001-ec54d159110f"
```

Do not rerun this command unless a new operator decision explicitly requires it.

The transcript was processed in three chunks. All six correction/structure
relay calls completed. Current artifact path:

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

Output evidence:

```text
manifest.json          1,506 bytes
summary.md            17,585 bytes
transcript.clean.txt  41,856 bytes
transcript.raw.srt   103,210 bytes
transcript.raw.txt    39,398 bytes
```

The raw transcript SHA-256 was identical before and after recovery:

```text
430A75970CB943B2AD4C6F81CC8CE986A5A7CF1C8A59F9F168D9084EAE18E702
```

Content-level smoke checks found three summary sections and no fallback,
timeout, `<think>`, or chunk-failure markers. This was technical contract
validation, not exhaustive human editorial review.

## Wave 009 Remaining Work

As rechecked on 2026-07-30:

- the recovered manifest remains `status=done` with `errors=[]`;
- the vBook run's `control/pause.request` still exists;
- no vBook reconciliation response has been observed in the vsync commits
  after the recovery result.

vtext must not delete the pause or rewrite vBook's two failed attempt records.
vBook owns artifact revalidation, task reconciliation, and pause resolution.
If vBook cannot reconcile the recovered artifact in place, it should create a
separate recovery record while retaining the original failed run history.

The recovery result was delivered through vsync:

| Commit | Message |
| --- | --- |
| `63a933f` | Published the blocking follow-up and chunked recovery plan |
| `c85ba19` | Reported successful controlled recovery and validation evidence |

Canonical result message:

```text
mailbox/messages/2026-07-22-vtext-vbook-allwin-wave-009-controlled-recovery-result-response.md
```

## New Priority: 7866 Gateway Change

The latest vsync remote `main` is `b434c1d` as of 2026-07-30. It delivers this
open action for vtext:

```text
mailbox/messages/2026-07-30-vision-vtext-7866-qwen-general-gateway-deployment-change-notice.md
Expected Executor: lcodex
Action Required: yes
```

Important deployed changes:

- `http://192.168.0.33:7866` remains the stable upstream URL;
- port 7866 is now the vision-managed `qwen-general` FastAPI gateway, not a
  remotely exposed raw Ollama listener;
- raw Ollama moved to loopback `127.0.0.1:11437` and must not be used by vtext;
- request bodies are limited to 2 MiB and oversized requests return HTTP 413;
- gateway connect timeout is 5 seconds and upstream read/write timeout is 300
  seconds, so vtext's `llm_timeout=900` cannot extend the gateway deadline;
- `qwen3.6:latest` is the platform baseline; `qwen3.5:9b` is currently present
  but vtext must explicitly decide and pin its intended model;
- long refine remains safer through bounded chunking.

The next session's first substantive task is to acknowledge this message and
send a focused internal `sync/c2s` request to lcodex. Required Linux evidence:

1. confirm deployed `ollama_url=http://192.168.0.33:7866` and no raw-port use;
2. decide and report the active model (`qwen3.5:9b` or `qwen3.6:latest`);
3. verify gateway health/version/tags/short chat and normal vtext `/llm/chat`;
4. run one representative bounded long-refine probe and record latency/request
   IDs around the 300-second gateway limit;
5. verify handling of HTTP 413, 503, upstream errors, and prematurely terminated
   streaming responses;
6. reply through internal sync, after which wcodex should send the durable vsync
   response to vision.

Do not change Windows client routing or the production model before lcodex
returns deployed evidence and an explicit compatibility recommendation.

## Repository State And Guardrails

vtext `main` is synchronized with `origin/main` at `ad22455`. Existing local
changes that predate this handoff must be preserved:

```text
 M docs/90_reference/README.md
?? docs/90_reference/vsync-adoption.md
?? var/
```

Do not stage, revert, or delete those paths as part of unrelated work.

The local `E:/projects/my_app/vsync` worktree is intentionally dirty and its
local `main` is behind `origin/main`. After a fetch on 2026-07-30,
`origin/main=b434c1d`. Do not reset, merge, or overwrite the existing vsync
working changes. For new mailbox commits, use a temporary clean worktree based
on `origin/main`, push it as a fast-forward to remote `main`, then remove the
temporary worktree and branch.

Windows PowerShell profile output can interfere with text inspection and can
display UTF-8 Chinese as mojibake when encoding is implicit. Use explicit UTF-8
or the `App` Python interpreter before concluding that a JSON artifact is
corrupt.

## Next Session Startup Checklist

1. Read `AGENTS.md` and this handoff.
2. Run `git status --short --branch` in vtext and preserve unrelated changes.
3. Fetch vsync without merging and inspect `origin/main` vtext inbox.
4. Process the 2026-07-30 7866 gateway notice through internal `sync/` with
   `Expected Executor: lcodex`.
5. Check whether vBook has replied to `c85ba19` or resolved the wave 009 pause.
6. Do not rerun wave 009 ASR/refine or mutate vBook run history without a new
   explicit operator request.
7. After any code change, use the Windows `App` interpreter and a local pytest
   basetemp, then report unavailable lint tools honestly.
