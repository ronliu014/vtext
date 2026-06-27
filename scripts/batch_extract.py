"""Driver: full-method knowledge extraction for a directory of videos.

Reuses vtext_client.batch._process_one (no library changes) but adds:
  - selects ONLY *.mp4
  - sends output to a SEPARATE tree (mirrors the source folder hierarchy)
  - resumes: skips a video whose _raw/_clean/_summary all already exist
  - server-relay refine by default (works when local Ollama is down)

Per video, under OUTPUT/<same-folder>/:
  <stem>_raw.<fmt>   - original ASR transcript
  <stem>_clean.txt   - corrected + simplified full text
  <stem>_summary.md  - structured reorganization

Usage:
  python scripts/batch_extract.py \
      --input  "F:/downloads/allwin/投资训练营" \
      --output "F:/downloads/output" \
      --jobs 2 --refine-mode server
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from vtext_client._batchprogress import BatchProgress, make_callback
from vtext_client.api import check_health
from vtext_client.batch import _process_one
from vtext_client.config import load_client_config
from vtext_client.errors import VtextClientError

# Defaults preserve the original douyin run (F:\vtext\input -> F:\vtext\output).
DEFAULT_INPUT = Path(r"F:\vtext\input")
DEFAULT_OUTPUT = Path(r"F:\vtext\output")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Full-method batch video extraction.")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                   help="Input root directory (recursively scanned for *.mp4).")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help="Output root; mirrors the input folder hierarchy.")
    p.add_argument("--fmt", default="txt", choices=["txt", "srt", "vtt"],
                   help="Raw transcript format.")
    p.add_argument("--jobs", type=int, default=2,
                   help="Parallel jobs (match the server's transcription workers).")
    p.add_argument("--refine-mode", default="server",
                   choices=["auto", "direct", "server"],
                   help="LLM refine path; 'server' relays via vtext-server.")
    p.add_argument("--llm-timeout", type=int, default=600,
                   help="Per-LLM-call timeout in seconds.")
    return p.parse_args()


def _already_done(video: Path, input_root: Path, output_root: Path, fmt: str) -> bool:
    rel = video.relative_to(input_root)
    out_dir = output_root / rel.parent
    stem = rel.stem
    return (
        (out_dir / f"{stem}_raw.{fmt}").exists()
        and (out_dir / f"{stem}_clean.txt").exists()
        and (out_dir / f"{stem}_summary.md").exists()
    )


def main() -> int:
    args = _parse_args()
    input_root: Path = args.input
    output_root: Path = args.output
    fmt: str = args.fmt

    if not input_root.is_dir():
        print(f"FATAL: input dir not found: {input_root}", file=sys.stderr)
        return 2

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

    output_root.mkdir(parents=True, exist_ok=True)

    all_videos = sorted(input_root.rglob("*.mp4"))
    todo = [v for v in all_videos if not _already_done(v, input_root, output_root, fmt)]
    skipped = len(all_videos) - len(todo)
    print(
        f"Input: {input_root}\nOutput: {output_root}\n"
        f"Found {len(all_videos)} mp4; {skipped} already done; "
        f"{len(todo)} to process with {args.jobs} parallel job(s); "
        f"refine_mode={args.refine_mode}.",
        file=sys.stderr,
    )
    if not todo:
        print("Nothing to do.", file=sys.stderr)
        return 0

    prog = BatchProgress([v.name for v in todo])
    prog.start()

    failures: list[tuple[Path, Exception]] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {}
        for idx, v in enumerate(todo):
            futures[
                pool.submit(
                    _process_one,
                    v,
                    base_dir=input_root,
                    text_dir=output_root,
                    server=server,
                    fmt=fmt,
                    language=cfg.default_language,
                    model=cfg.default_model,
                    simplify=False,
                    refine=True,
                    ollama_url=cfg.ollama_url,
                    refine_model=cfg.ollama_model,
                    refine_mode=args.refine_mode,
                    llm_timeout=args.llm_timeout,
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
