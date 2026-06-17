"""Batch processing for directories of audio/video files."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from .api import submit_job, stream_progress
from .audio import extract_wav, maybe_compress
from .errors import VtextClientError

SUPPORTED_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
}


def batch_transcribe(
    directory: Path,
    server: str,
    fmt: str,
    language: str | None,
    model: str | None,
    jobs: int,
) -> None:
    files = [
        f for f in sorted(directory.rglob("*"))
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if not files:
        click.echo(f"No supported media files found in {directory}", err=True)
        return

    # Create text/ subdir in the input directory
    text_dir = directory / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Found {len(files)} file(s). Processing with {jobs} parallel job(s).", err=True)
    click.echo(f"Output directory: {text_dir}", err=True)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(
                _process_one, f, text_dir=text_dir, server=server, fmt=fmt,
                language=language, model=model
            ): f
            for f in files
        }
        for future in as_completed(futures):
            f = futures[future]
            try:
                out_path = future.result()
                click.echo(f"  Done: {f.name} -> {out_path.name}", err=True)
            except VtextClientError as e:
                click.echo(f"  Failed: {f.name}: {e}", err=True)


def _process_one(
    input_path: Path,
    text_dir: Path,
    server: str,
    fmt: str,
    language: str | None,
    model: str | None,
) -> Path:
    wav_path = None
    upload_path = None
    try:
        wav_path = extract_wav(input_path)
        upload_path, encoding = maybe_compress(wav_path)
        job_id = submit_job(
            server, upload_path,
            encoding=encoding,
            language=language,
            fmt=fmt,
            model=model,
        )
        result = stream_progress(server, job_id)
        from vtext_common.formats import format_output
        text = result.formatted or format_output(result.segments, fmt)

        # Save to text_dir with input filename + .fmt extension
        out_path = text_dir / f"{input_path.stem}.{fmt}"
        out_path.write_text(text, encoding="utf-8")
        return out_path
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)
        if upload_path and upload_path != wav_path:
            upload_path.unlink(missing_ok=True)
