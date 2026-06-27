"""Batch processing for directories of audio/video files."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from ._batchprogress import BatchProgress, make_callback
from .api import submit_job, stream_progress
from .audio import extract_wav, maybe_compress
from .errors import VtextClientError
from .refine import refine_text, to_simplified

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
    refine: bool = False,
    ollama_url: str = "http://localhost:11434",
    refine_model: str = "qwen3.5:9b",
    refine_mode: str = "auto",
    llm_timeout: int = 300,
    output_dir: Path | None = None,
) -> None:
    # Output dir: when specified, mirror input hierarchy under it; otherwise
    # default to <directory>/text (backward compat). Create before scanning to
    # exclude it from the input set (avoid reprocessing our own outputs).
    if output_dir is not None:
        text_dir = output_dir
    else:
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
                    refine=refine,
                    ollama_url=ollama_url,
                    refine_model=refine_model,
                    refine_mode=refine_mode,
                    llm_timeout=llm_timeout,
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
    refine: bool = False,
    ollama_url: str = "http://localhost:11434",
    refine_model: str = "qwen3.5:9b",
    refine_mode: str = "auto",
    llm_timeout: int = 300,
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
            text = to_simplified(text)

        # Preserve the input's directory hierarchy under text/:
        # <dir>/sub/a.mp4 -> <dir>/text/sub/a_raw.<fmt>
        rel = input_path.relative_to(base_dir)
        out_dir = text_dir / rel.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = rel.stem
        out_path = out_dir / f"{stem}_raw.{fmt}"
        out_path.write_text(text, encoding="utf-8")

        # Refine: <stem>_clean.txt + <stem>_summary.md co-located with the raw.
        # Non-fatal: warn + skip on any failure (raw transcript is already saved).
        if refine:
            try:
                plain = result.text or format_output(result.segments, "txt")
                clean, summary = refine_text(
                    plain,
                    ollama_url=ollama_url,
                    model=refine_model,
                    server_url=server,
                    mode=refine_mode,
                    timeout=llm_timeout,
                )
                (out_dir / f"{stem}_clean.txt").write_text(clean, encoding="utf-8")
                (out_dir / f"{stem}_summary.md").write_text(summary, encoding="utf-8")
            except Exception as e:  # noqa: BLE001 - non-fatal refine step
                click.echo(
                    f"  Warning: refine skipped for {input_path.name}: {e}", err=True
                )

        return out_path
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)
        if upload_path and upload_path != wav_path:
            upload_path.unlink(missing_ok=True)
