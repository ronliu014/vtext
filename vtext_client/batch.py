"""Batch processing for directories of audio/video files."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from ._batchprogress import BatchProgress, make_callback
from .api import submit_job, stream_progress
from .audio import extract_wav, maybe_compress
from .errors import VtextClientError

SUPPORTED_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
}


def batch_transcribe(
    directory: Path,
    server: str,
    fmt: str,
    language: str | None,
    model: str | None,
    jobs: int,
    simplify: bool = False,
) -> None:
    # Output dir is <directory>/text; create it before scanning so we can
    # exclude it from the input set (avoid reprocessing our own outputs).
    text_dir = directory / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    files = [
        f
        for f in sorted(directory.rglob("*"))
        if f.is_file()
        and f.suffix.lower() in SUPPORTED_EXTENSIONS
        and text_dir not in f.parents
    ]
    if not files:
        click.echo(f"No supported media files found in {directory}", err=True)
        return

    click.echo(
        f"Found {len(files)} file(s). Processing with {jobs} parallel job(s).", err=True
    )
    click.echo(f"Output directory: {text_dir}", err=True)

    prog = BatchProgress([f.name for f in files])
    prog.start()

    failures: list[tuple[Path, VtextClientError]] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures: dict = {}
        for idx, f in enumerate(files):
            futures[
                pool.submit(
                    _process_one,
                    f,
                    base_dir=directory,
                    text_dir=text_dir,
                    server=server,
                    fmt=fmt,
                    language=language,
                    model=model,
                    simplify=simplify,
                    idx=idx,
                    on_progress=make_callback(prog, idx),
                )
            ] = idx
        for future in as_completed(futures):
            idx = futures[future]
            try:
                out_path = future.result()
                prog.file_done(idx, ok=True, out_name=out_path.name)
            except VtextClientError as e:
                failures.append((files[idx], e))
                prog.file_done(idx, ok=False, error=str(e))

    prog.finish()

    if failures:
        click.echo(f"\n{len(failures)} file(s) failed:", err=True)
        for f, e in failures:
            click.echo(f"  {f.name}: {e}", err=True)


def _process_one(
    input_path: Path,
    base_dir: Path,
    text_dir: Path,
    server: str,
    fmt: str,
    language: str | None,
    model: str | None,
    simplify: bool = False,
    idx: int = 0,
    on_progress=None,
) -> Path:
    wav_path = None
    upload_path = None
    try:
        if on_progress:
            on_progress(0)  # mark this file as active (shown at 0%)
        wav_path = extract_wav(input_path)
        upload_path, encoding = maybe_compress(wav_path)
        job_id = submit_job(
            server,
            upload_path,
            encoding=encoding,
            language=language,
            fmt=fmt,
            model=model,
        )
        result = stream_progress(server, job_id, on_progress=on_progress)
        from vtext_common.formats import format_output

        text = result.formatted or format_output(result.segments, fmt)
        if simplify:
            try:
                import opencc

                text = opencc.OpenCC("t2s").convert(text)
            except ImportError:
                pass

        # Preserve the input's directory hierarchy under text/:
        # <dir>/sub/a.mp4 -> <dir>/text/sub/a.<fmt>
        rel = input_path.relative_to(base_dir)
        out_path = text_dir / rel.with_suffix(f".{fmt}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        return out_path
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)
        if upload_path and upload_path != wav_path:
            upload_path.unlink(missing_ok=True)
