# vtext Task Board

Last updated: 2026-07-30

## Done

- Initialized CodeGraph for the repository.
- Added the vBook text integration response.
- Added `--bundle vbook` for single-video stable artifact output.
- Added per-lesson `manifest.json` support for vBook bundles.
- Documented the local Windows Anaconda `App` environment in `AGENTS.md`.
- Reorganized docs into lightweight numbered layers.
- Adapted the LLM relay to the qwen-general gateway with qwen3.6, request IDs,
  structured upstream errors, a 2 MiB request guard, and bounded chunked refine.
- Added 413, 503, timeout, malformed response, empty response, and truncated SSE tests.
- Completed live qwen-general, temporary current-code vtext relay, and 12,000
  character representative refine validation with request-ID, request-size, and
  latency evidence.

## Next

- Add explicit CLI metadata options for vBook bundle output:
  `--course`, `--series`, and `--lesson-title`.
- Add sample success and failure manifests under `docs/90_reference/samples/`.
- Create the reviewed vtext commit, then decide whether to deploy/restart
  production `:8000` and run the post-restart relay smoke test.
- Add batch-level manifest support if vBook needs course-scale invocation.

## Later

- Improve server upload streaming for very large files.
- Split long-term output contract details from historical integration
  request/response documents as the contract evolves.
