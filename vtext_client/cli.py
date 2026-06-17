"""CLI commands for vtext client."""
import sys
from pathlib import Path

import click

from .api import check_health, submit_job, stream_progress
from .audio import extract_wav, maybe_compress
from .batch import batch_transcribe
from .errors import QueueFullError, ServerConnectionError, VtextClientError
from vtext_common.formats import format_output


@click.command()
@click.argument("input", required=False)
@click.option("--server", envvar="VTEXT_SERVER_URL", default="http://127.0.0.1:8000",
              show_default=True, help="vtext-server URL")
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output file path (default: stdout)")
@click.option("-f", "--format", "fmt", type=click.Choice(["txt", "srt", "vtt"]),
              default="txt", show_default=True)
@click.option("-l", "--language", default=None, help="Language code, e.g. en, zh")
@click.option("-m", "--model", default=None, help="Override server default model")
@click.option("-j", "--jobs", default=1, show_default=True,
              help="Parallel jobs for batch processing")
@click.option("--check-server", is_flag=True, default=False,
              help="Check server health and exit")
def cli(input, server, output, fmt, language, model, jobs, check_server):
    """Transcribe audio/video files using vtext-server."""
    if check_server:
        _do_check_server(server)
        return

    if not input:
        raise click.UsageError("Please provide an input file or directory.")

    input_path = Path(input)
    if not input_path.exists():
        click.echo(f"Error: {input_path} does not exist.", err=True)
        sys.exit(1)

    if input_path.is_dir():
        batch_transcribe(input_path, server=server, fmt=fmt,
                         language=language, model=model, jobs=jobs)
        return

    _transcribe_file(input_path, server=server, output=output,
                     fmt=fmt, language=language, model=model)


def _transcribe_file(
    input_path: Path,
    server: str,
    output: str | None,
    fmt: str,
    language: str | None,
    model: str | None,
) -> None:
    wav_path = None
    upload_path = None
    try:
        click.echo(f"Extracting audio from {input_path.name}...", err=True)
        wav_path = extract_wav(input_path)

        upload_path, encoding = maybe_compress(wav_path)
        if encoding:
            click.echo("Compressing audio (zstd)...", err=True)

        click.echo("Submitting transcription job...", err=True)
        try:
            job_id = submit_job(
                server, upload_path,
                encoding=encoding,
                language=language,
                fmt=fmt,
                model=model,
            )
        except QueueFullError as e:
            click.echo(
                f"Error: {e}\nRetry later or use a different server.", err=True
            )
            sys.exit(1)

        click.echo(f"Job {job_id} queued. Waiting for result...", err=True)

        with click.progressbar(
            length=100, label="Transcribing", file=sys.stderr
        ) as bar:
            last = 0

            def on_progress(pct: int) -> None:
                nonlocal last
                bar.update(pct - last)
                last = pct

            result = stream_progress(server, job_id, on_progress=on_progress)
            bar.update(100 - last)

        text = result.formatted or format_output(result.segments, fmt)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            click.echo(f"Saved to {output}", err=True)
        else:
            click.echo(text)

    except (ServerConnectionError, VtextClientError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)
        if upload_path and upload_path != wav_path:
            upload_path.unlink(missing_ok=True)


def _do_check_server(server: str) -> None:
    try:
        info = check_health(server)
        click.echo(f"Server: {server}")
        click.echo(f"Status: {info.get('status')}")
        click.echo(f"Model:  {info.get('model', {}).get('loaded')}")
        q = info.get("queue", {})
        click.echo(f"Queue:  {q.get('size')}/{q.get('max')}")
        w = info.get("workers", {})
        click.echo(f"Workers: {w.get('busy')}/{w.get('total')} busy")
    except ServerConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
