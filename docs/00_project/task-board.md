# vtext Task Board

Last updated: 2026-07-07

## Done

- Initialized CodeGraph for the repository.
- Added the vBook text integration response.
- Added `--bundle vbook` for single-video stable artifact output.
- Added per-lesson `manifest.json` support for vBook bundles.
- Documented the local Windows Anaconda `App` environment in `AGENTS.md`.
- Reorganized docs into lightweight numbered layers.

## Next

- Add explicit CLI metadata options for vBook bundle output:
  `--course`, `--series`, and `--lesson-title`.
- Add sample success and failure manifests under `docs/90_reference/samples/`.
- Add a smoke fixture/runbook for one vBook lesson.
- Add batch-level manifest support if vBook needs course-scale invocation.

## Later

- Improve server upload streaming for very large files.
- Add richer server health checks for LLM relay readiness.
- Split long-term output contract details from historical integration
  request/response documents as the contract evolves.

