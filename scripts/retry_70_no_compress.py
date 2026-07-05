"""Retry 70 failed videos with compression disabled.

Before running: ensure COMPRESS_THRESHOLD in vtext_client/audio.py is set to 999999.
"""
from pathlib import Path
import sys
from vtext_client.config import load_client_config
from vtext_client.batch import _process_one
from vtext_client._batchprogress import BatchProgress, make_callback
from concurrent.futures import ThreadPoolExecutor, as_completed

INPUT = Path(r"F:\downloads\allwin\投资训练营")
OUTPUT = Path(r"F:\downloads\output")

cfg = load_client_config()

# Find 70 failed videos (those without _raw.txt)
all_vids = sorted(INPUT.rglob("*.mp4"))
out_raws = {r.stem[:-4] for r in OUTPUT.rglob("*_raw.txt")}
failed = [v for v in all_vids if v.stem not in out_raws]

print(f"Found {len(failed)} videos to retry (compression disabled)", flush=True)
print(f"Server: {cfg.server_url}", flush=True)
print()

prog = BatchProgress([v.name for v in failed])
prog.start()

failures = []
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = {}
    for idx, v in enumerate(failed):
        futures[
            pool.submit(
                _process_one,
                v,
                base_dir=INPUT,
                text_dir=OUTPUT,
                server=cfg.server_url,
                fmt="txt",
                language=cfg.default_language,
                model=cfg.default_model,
                simplify=False,
                refine=True,
                ollama_url=cfg.ollama_url,
                refine_model=cfg.ollama_model,
                refine_mode="server",
                llm_timeout=600,
                idx=idx,
                on_progress=make_callback(prog, idx),
            )
        ] = idx
    for future in as_completed(futures):
        idx = futures[future]
        try:
            out_path = future.result()
            prog.file_done(idx, ok=True, out_name=out_path.name)
        except Exception as e:
            failures.append((failed[idx], e))
            prog.file_done(idx, ok=False, error=str(e))

prog.finish()

print(f"\nDONE. ok={len(failed) - len(failures)} failed={len(failures)} total={len(failed)}", flush=True)
if failures:
    print(f"{len(failures)} file(s) still failed:", flush=True)
    for f, e in failures:
        print(f"  {f.name}: {e}", flush=True)
    sys.exit(1)
