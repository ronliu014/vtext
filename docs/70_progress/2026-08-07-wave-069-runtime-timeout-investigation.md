# Wave 069 qwen-general Runtime Timeout Investigation

Date: 2026-08-07
Updated: 2026-08-08
Status: service fix deployed; host clock aligned; vision verification pending
Decision: `service_deployed_clock_gate_verification_pending`

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
vision correlated the failure to a 49.63-second qwen3.6 cold load followed by
a long non-streaming generation. Together they crossed qwen-general's
300-second pre-header read-inactivity boundary. The successful calls completed
with the already-warm model and do not provide cold-start headroom.

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

Read-only qwen-general checks returned healthy, Ollama runtime 0.20.7. vision
confirmed the event used one qwen3.6 runner, with `OLLAMA_NUM_PARALLEL=1`, and
no overlapping Ollama execution. The later `qwen3.5:9b` observation was caused
by a load at `15:58:40+08:00`; it was not resident and did not switch during
Wave 069.

## Timeout Layers

The 900-second vtext value is the caller HTTP wait budget. qwen-general 1.1.0,
from code/config source commit `95a4514e71305520d95855d94236274133a75f63`,
independently enforces a 300-second gateway-to-Ollama read and write inactivity
window. With `stream=false`, Ollama does not return the final response headers
and body until generation completes.

The exact expired operation was an `httpx.ReadTimeout` while waiting for
upstream response headers. qwen-general returned HTTP 504 at 300.009 seconds,
before vtext's 900-second budget expired. Ollama recorded HTTP 500 after
exactly five minutes in the same second, consistent with propagated client
cancellation; there is no evidence that work continued after the gateway 504.
Raising the vtext timeout cannot extend this gateway-owned boundary.

## Concurrency Decision

Two concurrent CLI jobs are functionally supported by admission into the
single-worker queue, but this workload is not compatible with a clean two-job
production canary latency envelope. One 277-second execution behind another
request already produced about 525 seconds from submission to completion.

Keep `llm_workers=1` until vision provides runtime-capacity evidence. Increasing
workers could increase GPU contention and model churn. Do not increase the
900-second caller timeout, create a vBook-only route, or allow direct GPU access.

## Vision Runtime Correlation

vision preserved the qwen-general, Ollama, service, GPU, host, and Windows
event evidence without restarting a service, changing configuration, or making
a model call. The primary request reached qwen-general at
`06:38:17.333415` on the gateway clock and returned HTTP 504 at
`06:43:17.342415`, after 300.009 seconds. The approximately 29-second clock
difference from the Linux vtext timestamps must be corrected before another
cross-host canary.

Ollama started the qwen3.6 runner at `14:38:17.537+08:00`; it became available
49.63 seconds later. The runner used partial CPU offload but had sufficient
system, swap, and GPU memory. There was no OOM, allocation failure, GPU error,
runtime panic, model switch, or overlapping Ollama execution in the incident
window. Historical GPU utilization and prompt-eval/generation token metrics
were not retained; these are explicit observability gaps, not evidence of the
timeout cause.

The redacted vision diagnostic archive remains at
`D:/vision/logs/diagnostics/platform-20260807-165017.zip`, SHA-256
`c5a0b765bfb677645626fb75ea0d31d16e3908826a2277a74ae19eec9951e356`.
It is intentionally excluded from Git.

## Shared-Service Remediation

vision deployed qwen-general 1.2.0 from revision
`81bae31ffc7c7bb9e2762077a3e588034b0e13aa`, effective-config SHA-256
`5565052f95dbe7bdac7fb39bf733552c953c94498dcc4be94e67137b4c5641be`.
The deployed gateway retains five-second connect/pool and 300-second write
timeouts while raising the pre-header read boundary to 600 seconds. It also
exposes content-free phase telemetry, model-aware single-runtime FIFO
admission, a bounded 16-request queue, `GET /queue`, and build/config identity.

Only the qwen-general gateway was restarted for that deployment. Ollama was
not restarted, and vision made no model call because the cross-host clock gate
still failed. The remaining clock blocker was corrected on the vtext Linux
host on 2026-08-08; vision independent acceptance is pending.

## Host Clock Alignment

Before correction, `timedatectl` reported `System clock synchronized: no` and
chrony was Stratum 0 with no selectable source. Four internal NTP probes agreed
that the Linux clock was fast by 29.161455 to 29.162874 seconds. The managed
source file is `/etc/chrony/sources.d/lr-internal.sources`, SHA-256
`f4d453ff1379c15187e79bb9423bcfe5d22e4e1ade103daebeba666d8bce267c`,
with four `trust require` internal sources.

chrony selected `192.168.15.241` (`dc02.lr.local` on vision) and stepped the
system clock backward by 29.161155 seconds. Post-correction evidence shows
Stratum 4, `Leap status: Normal`, `System clock synchronized: yes`, and an
independent NTP offset of -0.000672 seconds. vtext remained PID `314620` and
was not restarted.

Three consecutive qwen-general HTTP Date midpoint measurements had 3 ms RTT
and absolute offsets of 0.5265, 0.6115, and 0.6545 seconds. Ten simultaneous
vtext/qwen-general Date samples differed by at most one second; seven matched
exactly. Both services were healthy with empty queues and idle workers.

The durable vtext-to-vision evidence is
`mailbox/messages/2026-08-08-vtext-vision-wave-069-clock-alignment-evidence-response.md`
in vsync commit `fc7f303`. Clock alignment does not authorize a cold/warm
probe, canary, scheduler resume, or production recovery.

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

Do not rerun Wave 069. A two-job canary is not authorized now. It may be
reconsidered only after the service fix is separately approved, deployed, and
verified with effective OpenAPI/config evidence for the 600-second boundary,
observable build identity, and vtext/vision clocks aligned within one second.

Before that canary, separately authorize representative cold and warm probes
with qwen3.6 exact model/blob identity recorded, no competing model load, one
Ollama runner, and an empty initial queue. Each probe must succeed on its first
attempt below 450 seconds, preserving at least 150 seconds of headroom under
the proposed boundary, with no retry, 5xx, OOM, model switch, or residual work.

For a later separately operator-authorized two-job canary, retain
`llm_workers=1`, route only through vtext, capture job/request IDs and all queue
and upstream timing evidence, and require all correction and structure calls
to succeed on the first attempt with valid manifests. Reject any automatic
retry, fallback, 429, 5xx, model switch, unexplained queue state, or residual
work. An automatic retry remains operational recovery but makes the canary
degraded.

The earlier provisional 270-second clean threshold is superseded for this
service-envelope test because retained warm production calls took 272.219,
276.934, and 287.571 seconds. A stricter business SLO would require a separately
bounded workload/model profile and cannot be represented as the current qwen3.6
service envelope.

No vtext restart, request, model call, retry, probe, canary, scheduler resume,
or production recovery occurred during clock correction. Only chrony was
reconfigured and restarted to apply the managed host time source.
