# Wave 069 qwen-general Runtime Timeout Investigation

Date: 2026-08-07
Updated: 2026-08-09
Status: two-job canary technical pass; authorization provenance pending
Decision: `technical_pass_procedural_evidence_pending`

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
not restarted. The remaining clock blocker was corrected on the vtext Linux
host on 2026-08-08. vision independently accepted the corrected clock gate and
then completed the separately approved one-cold/one-warm qualification window.

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
in vsync commit `fc7f303`.

## Service Qualification And Canary Decision

vision independently retained the one-second clock gate. After waiting for
the Uvicorn second-granularity Date header to advance, its three consecutive
absolute cross-host offsets were 0.558, 0.512, and 0.559 seconds.

vision then used its already approved probe window for exactly one cold and one
identical warm representative qwen3.6 request. Both used the same 16,124-byte
synthetic non-streaming body, completed on their first attempt, and returned
the same 2,517-character response digest:
`08953360f96909a9da25e73a294492f71d06e622a33190389bef60f39781a082`.

| Probe | Request ID | Result | Wall time | Load time | 600-second headroom |
| --- | --- | --- | ---: | ---: | ---: |
| Cold | `wave069-clockfix-cold-20260808` | HTTP 200, `done=true`, stop | 268.327 s | 55.124 s | 331.673 s |
| Warm | `wave069-clockfix-warm-20260808` | HTTP 200, `done=true`, stop | 148.781 s | 0.203 s | 451.219 s |

Both probes had zero queue wait. There was no retry, 429, 5xx, timeout, model
switch, OOM, second model load, or residual queue work. The effective service
was qwen-general 1.2.0 revision `81bae31ffc7c7bb9e2762077a3e588034b0e13aa`,
config SHA-256
`5565052f95dbe7bdac7fb39bf733552c953c94498dcc4be94e67137b4c5641be`,
with model manifest digest
`07d35212591fc27746f0a317c975a6d68754fb38e9053d82e25f06057af28522`.

The durable vision qualification is
`mailbox/messages/2026-08-08-vision-vtext-wave-069-clock-and-probe-qualification-response.md`
in vsync commit `5ff710d`. The service classification is now
`service_fix_verified`.

The vText compatibility decision is
`service_fix_verified_canary_window_pending`: the technical prerequisites for
a strictly bounded two-job canary are satisfied. This is not execution
authorization. vBook must keep the scheduler paused and wait for an explicit
operator window naming the two canary jobs. Wave 069 must not be rerun, and no
publication, delivery, general production recovery, or scheduler resume is
authorized by this decision.

## Two-Job Canary Correlation And Result

The vBook prelaunch acknowledgement reports one relative 90-minute operator
window for exactly two named non-Wave-069 jobs. vBook started the locked runner at
`2026-08-08T21:54:55.489805+08:00`, completed at
`2026-08-08T22:19:05.019537+08:00`, and did not approach the authorized
`23:24:55.489805+08:00` end. The global scheduler remained paused.

The two selected tasks and their vtext ASR jobs were:

- `001-55bad8cf7b12` / `基础教学/小白K线基础课/62、头肩底`:
  ASR job `2e7c9489`;
- `002-e50e0a2b93b7` / `基础教学/小白K线基础课/63、圆弧顶`:
  ASR job `f94fc004`.

Both ASR jobs completed with one vBook attempt. The client manifests reported
`status=done` and `errors=[]`. The two-stage client pipeline and immediate
enqueue sequence correlate exactly four LLM calls:

| Task / stage | LLM job / request ID | Request bytes | vtext FIFO wait | Upstream elapsed | Enqueue-to-done | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `002` correction | `56cc2639` / `0ad3096a3b9546889591aa9834eaf888` | 16,182 | 0.001244 s | 280.148 s | 280.150775 s | done, HTTP 200 |
| `001` correction | `275bc995` / `b1fe14da93a74a1a9483a3dc0174a648` | 20,588 | 160.999597 s | 291.326 s | 452.326866 s | done, HTTP 200 |
| `002` structure | `ee3e8ee7` / `2529498c13b94f3cb8ca79c81bda2100` | 11,808 | 291.060386 s | 250.366 s | 541.427670 s | done, HTTP 200 |
| `001` structure | `c4e20889` / `aa18f17e3bc243e18f72d004b49e8dc1` | 10,831 | 250.227666 s | 255.313 s | 505.541920 s | done, HTTP 200 |

Precise enqueue, worker-acquire, and completion timestamps are retained in
`journalctl --user -u vtext.service`:

| LLM job | Enqueued | Worker start | Worker end |
| --- | --- | --- | --- |
| `56cc2639` | `22:01:07.778046+08:00` | `22:01:07.779290+08:00` | `22:05:47.928821+08:00` |
| `275bc995` | `22:03:06.932789+08:00` | `22:05:47.932386+08:00` | `22:10:39.259655+08:00` |
| `ee3e8ee7` | `22:05:48.202915+08:00` | `22:10:39.263301+08:00` | `22:14:49.630585+08:00` |
| `c4e20889` | `22:10:39.406174+08:00` | `22:14:49.633840+08:00` | `22:19:04.948094+08:00` |

The upstream limit applies to each worker-to-gateway execution, not to vtext
FIFO wait plus execution. All four upstream executions were below 450 seconds.
The three longer enqueue-to-done values are expected serialization under the
required single LLM worker and are not timeout-boundary failures.

The dynamic canary-window journal contains exactly four LLM queued/start/done
chains, all using `qwen3.6:latest` and ending with HTTP 200. There is no
vtext-side retry, fallback, queue-full/429, 5xx, timeout, upstream error, model
change, unexplained queue event, or extra LLM call. vBook independently
reported no retry, fallback, OOM, second model load, invalid manifest, residual
work, or extra task.

Postflight read-only checks found:

- vtext ASR and LLM jobs all retained as `done`;
- vtext HTTP health `ok`, ASR workers `2/0 busy`, LLM workers `1/0 busy`,
  ASR queue `0/16`, and LLM queue `0/16`;
- the unchanged vtext main PID `314620`, active since
  `2026-07-30T07:35:47Z`;
- qwen-general 1.2.0 revision
  `81bae31ffc7c7bb9e2762077a3e588034b0e13aa`, unchanged config SHA-256
  `5565052f95dbe7bdac7fb39bf733552c953c94498dcc4be94e67137b4c5641be`,
  healthy with inactive admission and zero waiting.

qwen-general exposes current `/health` and `/queue` state plus response
headers, but no request-ID historical telemetry endpoint. vtext did retain the
required request IDs, request sizes, FIFO waits, worker timing, HTTP results,
and full worker-to-gateway elapsed times. This observability limit does not
change the result because all four complete upstream intervals were measured,
the required single vtext LLM worker prevented overlapping submissions, and
the client and gateway observations found no stop condition.

The vBook canary-window acknowledgement was committed as vsync `3f33792`
before execution and states that the operator authorized the exact two tasks,
relative 90-minute window, and retained pauses. vision has separately requested
the underlying operator-approval provenance because the acknowledgement is a
vBook assertion rather than the originating operator record. A later
2026-08-09 preparation approval cannot be used retroactively.

The independent vText technical result is `pass`. Formal classification is
`technical_pass_procedural_evidence_pending` until vBook returns one of
`authorization_provenance_confirmed`,
`authorization_provenance_unavailable`, or
`authorization_scope_mismatch`. This closes technical correlation only. It
does not authorize scheduler resume, publication, delivery, Vault writes,
another task/probe/canary, or general production recovery.

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

Do not rerun Wave 069. The service deployment, clock, representative cold/warm
qualification, and two-job canary technical gates are complete. The canary is
a technical pass under the defined service envelope, but formal acceptance is
pending the execution-authorization provenance requested by vision. Any
scheduler resume, publication, delivery, Vault write, or general production
recovery requires both procedural closure and a new explicit operator decision.

The earlier provisional 270-second clean threshold is superseded for this
service-envelope test because retained warm production calls took 272.219,
276.934, and 287.571 seconds. A stricter business SLO would require a separately
bounded workload/model profile and cannot be represented as the current qwen3.6
service envelope.

No vtext restart or configuration change occurred during the two-job canary or
result review. Exactly the four correlated LLM calls above ran in the approved
window. No later request, retry, probe, canary, scheduler resume, publication,
delivery, Vault write, or production recovery was performed by this review.
