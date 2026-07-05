"""Retry remaining failed videos after queue clears.

This script finds all videos that don't have _summary.md and processes them.
Run after server queue is nearly empty (size < 5).
"""
from pathlib import Path
import sys
import time
import requests
from vtext_client.config import load_client_config
from vtext_client.batch import submit_job, extract_wav, maybe_compress
from vtext_client.refine import refine_text

INPUT = Path(r"F:\downloads\allwin\投资训练营")
OUTPUT = Path(r"F:\downloads\output")

cfg = load_client_config()

def check_queue():
    """Check server queue size."""
    try:
        r = requests.get(f"{cfg.server_url}/health", timeout=5)
        return r.json()["queue"]["size"]
    except:
        return 999

# Find remaining failed videos
all_vids = sorted(INPUT.rglob("*.mp4"))
out_sums = {s.stem[:-8] for s in OUTPUT.rglob("*_summary.md")}
remaining = [v for v in all_vids if v.stem not in out_sums]

print(f"Found {len(remaining)} videos to process (compression disabled)", flush=True)
print(f"Server: {cfg.server_url}", flush=True)
print()

ok = 0
errors = []

for i, video in enumerate(remaining, 1):
    # Check queue before each submission
    q = check_queue()
    if q > 15:
        print(f"[{i}/{len(remaining)}] Queue too full ({q} jobs), pausing 5min...", flush=True)
        time.sleep(300)
        continue

    print(f"[{i}/{len(remaining)}] {video.name} (queue: {q})", flush=True)

    # Determine output paths
    rel = video.relative_to(INPUT)
    out_dir = OUTPUT / rel.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = video.stem

    raw_path = out_dir / f"{stem}_raw.txt"
    clean_path = out_dir / f"{stem}_clean.txt"
    summary_path = out_dir / f"{stem}_summary.md"

    try:
        # 1. Extract audio
        wav = extract_wav(video)

        # 2. Maybe compress (disabled by COMPRESS_THRESHOLD=999999)
        upload_path, encoding = maybe_compress(wav)

        # 3. Submit transcription
        result = submit_job(
            cfg.server_url,
            upload_path,
            encoding=encoding,
            language="zh",
            model="small"
        )

        # Clean up temp files
        wav.unlink(missing_ok=True)
        if upload_path != wav:
            upload_path.unlink(missing_ok=True)

        # 4. Save raw
        raw_path.write_text(result, encoding="utf-8")

        # 5. Refine (clean + summary)
        try:
            clean, summary = refine_text(
                result,
                ollama_url=cfg.ollama_url,
                model=cfg.ollama_model,
                server_url=cfg.server_url,
                mode="server",
                timeout=600
            )
            clean_path.write_text(clean, encoding="utf-8")
            summary_path.write_text(summary, encoding="utf-8")
            print(f"  OK (raw + clean + summary)", flush=True)
        except Exception as e:
            print(f"  WARNING refine failed: {e}", flush=True)
            print(f"  OK raw saved", flush=True)

        ok += 1

    except Exception as e:
        errors.append((video.name, str(e)))
        print(f"  FAIL: {e}", flush=True)
        # Don't abort on single failure, continue

    print(flush=True)

print(f"\nDONE. ok={ok} failed={len(errors)} total={len(remaining)}", flush=True)
if errors:
    print(f"\n{len(errors)} still failed:", flush=True)
    for name, err in errors[:10]:  # Show first 10
        print(f"  {name}: {err}", flush=True)
    if len(errors) > 10:
        print(f"  ... and {len(errors) - 10} more", flush=True)
