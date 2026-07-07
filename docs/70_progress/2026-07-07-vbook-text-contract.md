# 2026-07-07 vBook Text Contract

## Summary

vtext aligned with vBook's cross-project coordination request by documenting and
implementing a stable per-lesson text artifact contract.

## Changes

- Added `docs/90_reference/vbook-text-integration-response.md`.
- Added `--bundle vbook` for single-video CLI calls.
- Added `manifest.json` output for vBook per-lesson bundles.
- Added stable output names:
  - `transcript.raw.txt`
  - `transcript.raw.srt`
  - `transcript.clean.txt`
  - `summary.md`
- Documented the local Windows Anaconda `App` environment.
- Reorganized docs into lightweight numbered layers inspired by vBook.

## Verification

Using `D:\anaconda3\envs\App\python.exe`:

```text
tests/test_client: 89 passed
```

## Follow-Ups

- Add explicit metadata options for course, series, and lesson title.
- Add sample manifests under `docs/90_reference/samples/`.
- Decide whether vBook needs batch-level manifest support.

