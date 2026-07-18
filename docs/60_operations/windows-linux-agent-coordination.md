# Windows / Linux Agent Coordination

Status: active
Updated: 2026-07-18

This runbook defines how vtext work is split between the Windows-side agent
(`wcodex`) and the Linux-side agent (`lcodex`) when coordinating with vBook
through `vsync`.

## Context

The local Windows checkout is the main workspace for vault files, Allwin source
video paths, vBook coordination, and user-facing note review. The deployed
vtext service runs on a Linux server and is the authority for service-side code,
runtime configuration, process management, model availability, logs, and
production health.

`vsync` is deployed where both Windows and Linux agents can exchange mailbox
messages through git. The mailbox remains project-scoped: both `wcodex` and
`lcodex` act for the `vtext` participant and should read
`mailbox/inbox/vtext/README.md`.

## Agent Roles

### wcodex

`wcodex` is the Windows-side vtext agent.

Responsibilities:

- Coordinate with the user on local Windows paths, especially `F:/downloads`,
  `F:/vault`, and local `E:/projects/my_app/*` checkouts.
- Produce, inspect, and commit vault-facing vtext notes under
  `F:/vault/20_Learning/vtext`.
- Maintain vtext documentation, artifact contracts, and Windows-side runbooks.
- Reply to vBook when the work concerns local artifacts, source-note layout,
  vault commits, or Windows batch preparation.
- Ask `lcodex` through `vsync` when deployed service changes are required.

`wcodex` should not directly assume that local Windows changes are deployed on
the Linux service. It may prepare code or docs locally, but service rollout is
owned by `lcodex`.

### lcodex

`lcodex` is the Linux-side vtext agent.

Responsibilities:

- Maintain and modify the deployed Linux vtext service.
- Apply service-side code changes, install dependencies, update configuration,
  restart services, inspect logs, and verify health on the Linux host.
- Report deployment status, health, queue behavior, model availability, and
  runtime limits through `vsync`.
- Implement Linux-only operational changes that vBook needs immediately, such
  as timeout tuning, worker count changes, model upgrades, or service fixes.
- Coordinate back to `wcodex` when a service change requires Windows-side docs,
  vault artifacts, or source-note production changes.

`lcodex` should not write vBook or vault publication artifacts directly unless
the user explicitly assigns that Windows/vault responsibility to it.

### vBook Windows Agent

vBook remains the integration-hub side of the workflow.

Responsibilities:

- Audit production queues and detect available vtext/vision artifacts.
- Consume `F:/vault/20_Learning/vtext` read-only.
- Create preview batches, run preflight checks, and hold publication for user
  approval.
- Send vtext requests through `vsync` when source notes, manifests, transcripts,
  service behavior, or text quality gates are needed.
- Send service-runtime requests to `vtext` and explicitly mark whether the
  expected executor is `lcodex`, `wcodex`, or either.

## Routing Rules

Use these routing rules in `vsync` messages:

- `To: vtext`, `Owner: vtext`, `Expected Executor: wcodex` for Windows/vault
  artifact work.
- `To: vtext`, `Owner: vtext`, `Expected Executor: lcodex` for deployed Linux
  service work.
- `To: vtext`, `Owner: vtext`, `Expected Executor: wcodex + lcodex` when both
  local artifacts and service behavior must change.
- `To: vbook` for vBook queue, preview, or publication-side work.
- `To: all` for cluster-wide decisions or operating-model notices.

`Expected Executor` is not a new protocol field yet; include it in the message
body under `## Required Actions` or `## Routing`.

## Standard Workflows

### vBook Needs More Source Notes

1. vBook sends a request to `vtext` with `Expected Executor: wcodex`.
2. `wcodex` produces source notes and optional bundles.
3. `wcodex` commits/pushes vault changes.
4. `wcodex` replies through `vsync` with paths, manifest schema, failures, and
   quality caveats.
5. vBook patrols again and continues preview generation.

### vBook Needs Service Behavior Changed

1. vBook sends a request to `vtext` with `Expected Executor: lcodex`.
2. `lcodex` updates or verifies the Linux service.
3. `lcodex` replies through `vsync` with commit, deployment, health, and log
   evidence.
4. `wcodex` updates vtext docs only if a durable contract, default, or runbook
   changed.

### vtext Needs Both Local And Deployed Changes

1. `wcodex` or vBook opens a `vsync` request that names both executors.
2. `lcodex` handles deployed service work.
3. `wcodex` handles Windows/vault/docs work.
4. The final responder sends one consolidated result or links both responses
   with `In-Reply-To`.

## Current Service Boundary

The currently known production service endpoint is:

```text
http://192.168.0.122:8000
```

Use the vtext client health check before production batches:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client --server 'http://192.168.0.122:8000' --check-server
```

Linux-side service changes should be verified by `lcodex` from the deployed
host, not inferred from Windows-only checks.

## Guardrails

- Do not let vBook import or vendor vtext internals.
- Do not let Windows vault artifacts imply Linux service deployment.
- Do not use chat history as the durable coordination record.
- Keep canonical cross-project coordination in `vsync/mailbox/messages`.
- Keep large videos, transcripts, generated notes, and logs out of `vsync`; link
  paths and summarize.
- Record degraded outputs, timeout fallbacks, and semantic uncertainty in
  manifests and `vsync` responses.
