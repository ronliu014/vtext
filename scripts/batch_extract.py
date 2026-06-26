"""One-off driver: full-method knowledge extraction for F:/vtext/input.

Reuses vtext_client.batch._process_one (no library changes) but:
  - selects ONLY *.mp4 (each source folder also has a _music.mp3 we must skip)
  - sends output to a SEPARATE tree (batch mode normally hardcodes <input>/text)
  - mirrors the source folder hierarchy under the output root
  - resumes: skips a video whose _raw/_clean/_summary all already exist

Per video, under OUTPUT/<same-folder>/:
  <stem>_raw.<fmt>   - original ASR transcript
  <stem>_clean.txt   - corrected + simplified full text
  <stem>_summary.md  - structured reorganization
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from vtext_client._batchprogress import BatchProgress, make_callback
from vtext_client.api import check_health
from vtext_client.batch import _process_one
from vtext_client.config import load_client_config
from vtext_client.errors import VtextClientError

INPUT_ROOT = Path(r"F:\vtext\input")
OUTPUT_ROOT = Path(r"F:\vtext\output")
FMT = "txt"
JOBS = 2            # server has 2 transcription workers
REFINE_MODE = "server"  # local Ollama is down; use the server LLM relay
LLM_TIMEOUT = 600


def _already_done(video: Path) -> bool:
    rel = video.relative_to(INPUT_ROOT)
    out_dir = OUTPUT_ROOT / rel.parent
    stem = rel.stem
    return (
        (out_dir / f"{stem}_raw.{FMT}").exists()
        and (out_dir / f"{stem}_clean.txt").exists()
        and (out_dir / f"{stem}_summary.md").exists()
    )


def main() -> int:
    cfg = load_client_config()
    server = cfg.server_url

    print(f"Server: {server}", file=sys.stderr)
    try:
        info = check_health(server)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: server unreachable: {e}", file=sys.stderr)
        return 2
    print(
        f"Health: {info.get('status')} model={info.get('model', {}).get('loaded')} "
        f"workers={info.get('workers', {})}",
        file=sys.stderr,
    )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    all_videos = sorted(INPUT_ROOT.rglob("*.mp4"))
    todo = [v for v in all_videos if not _already_done(v)]
    skipped = len(all_videos) - len(todo)
    print(
        f"Found {len(all_videos)} mp4; {skipped} already done; "
        f"{len(todo)} to process with {JOBS} parallel job(s).",
        file=sys.stderr,
    )
    if not todo:
        print("Nothing to do.", file=sys.stderr)
        return 0

    prog = BatchProgress([v.name for v in todo])
    prog.start()

    failures: list[tuple[Path, Exception]] = []
    with ThreadPoolExecutor(max_workers=JOBS) as pool:
        futures = {}
        for idx, v in enumerate(todo):
            futures[
                pool.submit(
                    _process_one,
                    v,
                    base_dir=INPUT_ROOT,
                    text_dir=OUTPUT_ROOT,
                    server=server,
                    fmt=FMT,
                    language=cfg.default_language,
                    model=cfg.default_model,
                    simplify=False,
                    refine=True,
                    ollama_url=cfg.ollama_url,
                    refine_model=cfg.ollama_model,
                    refine_mode=REFINE_MODE,
                    llm_timeout=LLM_TIMEOUT,
                    idx=idx,
                    on_progress=make_callback(prog, idx),
                )
            ] = idx
        for future in as_completed(futures):
            idx = futures[future]
            try:
                out_path = future.result()
                prog.file_done(idx, ok=True, out_name=out_path.name)
            except (VtextClientError, Exception) as e:  # noqa: BLE001
                failures.append((todo[idx], e))
                prog.file_done(idx, ok=False, error=str(e))

    prog.finish()

    print(
        f"\nDONE. ok={len(todo) - len(failures)} failed={len(failures)} "
        f"skipped={skipped} total={len(all_videos)}",
        file=sys.stderr,
    )
    if failures:
        print(f"{len(failures)} file(s) failed:", file=sys.stderr)
        for f, e in failures:
            print(f"  {f.name}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
