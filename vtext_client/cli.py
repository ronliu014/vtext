"""CLI commands for vtext client."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from .api import check_health, submit_job, stream_progress
from .audio import extract_wav, maybe_compress
from .batch import batch_transcribe
from .config import load_client_config
from .errors import QueueFullError, RefineError, ServerConnectionError, ServerError, VtextClientError
from .manifest import error_entry, write_lesson_manifest
from .refine import refine_text, to_simplified
from vtext_common.formats import format_output


def _build_cli():
    """Build the CLI command with TOML defaults baked in as click defaults."""
    cfg = load_client_config()

    @click.command()
    @click.argument("input", required=False)
    @click.option("--server", default=cfg.server_url, show_default=True,
                  help="vtext-server URL")
    @click.option("-o", "--output", type=click.Path(), default=None,
                  help="Output path/dir. Single file: default <stem>_raw.<fmt> "
                       "next to input (use '-' for stdout). Batch: default "
                       "<input>/text/; specify dir to mirror input hierarchy.")
    @click.option("-f", "--format", "fmt",
                  type=click.Choice(["txt", "srt", "vtt"]),
                  default=cfg.default_format, show_default=True)
    @click.option("--bundle",
                  type=click.Choice(["legacy", "vbook"]),
                  default="legacy", show_default=True,
                  help="Artifact layout contract. Use 'vbook' for manifest bundle output.")
    @click.option("-l", "--language", default=cfg.default_language,
                  help="Language code, e.g. en, zh")
    @click.option("-m", "--model", default=cfg.default_model,
                  help="Override server default transcription model")
    @click.option("-j", "--jobs", default=cfg.default_jobs, show_default=True,
                  help="Parallel jobs for batch processing")
    @click.option("--simplify", is_flag=True, default=False,
                  help="Convert raw transcript Traditional -> Simplified (opt-in; "
                       "refine already yields a simplified clean text)")
    @click.option("--check-server", is_flag=True, default=False,
                  help="Check server health and exit")
    # --- refine (post-transcription LLM correction + structuring) ---
    @click.option("--no-refine", is_flag=True, default=False,
                  help="Disable refine (no clean/summary produced)")
    @click.option("--refine-only", is_flag=True, default=False,
                  help="Skip transcription; refine existing .txt file(s) instead")
    @click.option("--ollama", "ollama_url", default=cfg.ollama_url, show_default=True,
                  help="Ollama URL for direct refine (fallback: server relay)")
    @click.option("--refine-model", default=cfg.ollama_model, show_default=True,
                  help="Ollama model for refine")
    @click.option("--refine-mode",
                  type=click.Choice(["auto", "direct", "server"]),
                  default=cfg.refine_mode, show_default=True,
                  help="auto=direct-then-relay; direct=Ollama only; server=relay only")
    def _cli(input, server, output, fmt, bundle, language, model, jobs, simplify,
             check_server, no_refine, refine_only, ollama_url, refine_model,
             refine_mode):
        """Transcribe audio/video and (by default) refine into clean + summary.

        Default pipeline per source file:
          <stem>_raw.<fmt>  - original ASR transcript
          <stem>_clean.txt  - corrected + simplified full text
          <stem>_summary.md - structured reorganization
        """
        if check_server:
            _do_check_server(server)
            return

        if not input:
            raise click.UsageError("Please provide an input file or directory.")

        input_path = Path(input)
        if not input_path.exists():
            click.echo(f"Error: {input_path} does not exist.", err=True)
            sys.exit(1)

        refine = cfg.refine_enabled and not no_refine

        if refine_only:
            _refine_only(input_path, server=server, ollama_url=ollama_url,
                         model=refine_model, mode=refine_mode,
                         timeout=cfg.llm_timeout)
            return

        if input_path.is_dir():
            if bundle != "legacy":
                raise click.UsageError("--bundle vbook is currently single-file only.")
            if output == "-":
                raise click.UsageError(
                    "Batch mode does not support stdout output (--output -)."
                )
            output_path = Path(output) if output else None
            batch_transcribe(
                input_path,
                output_dir=output_path,
                server=server, fmt=fmt,
                language=language, model=model, jobs=jobs,
                simplify=simplify, refine=refine,
                ollama_url=ollama_url, refine_model=refine_model,
                refine_mode=refine_mode, llm_timeout=cfg.llm_timeout
            )
            return

        if bundle == "vbook":
            if not output or output == "-":
                raise click.UsageError("--bundle vbook requires --output <lesson-output-dir>.")
            if not refine:
                raise click.UsageError("--bundle vbook requires refine to be enabled.")
            if refine_mode == "direct":
                raise click.UsageError(
                    "--bundle vbook requires server-side refine; "
                    "use --refine-mode server or auto."
                )
            _transcribe_vbook_bundle(
                input_path,
                server=server,
                output_dir=Path(output),
                fmt=fmt,
                language=language,
                model=model,
                simplify=simplify,
                refine=refine,
                ollama_url=ollama_url,
                refine_model=refine_model,
                refine_mode="server",
                llm_timeout=cfg.llm_timeout,
            )
            return

        _transcribe_file(input_path, server=server, output=output,
                         fmt=fmt, language=language, model=model,
                         simplify=simplify, refine=refine,
                         ollama_url=ollama_url, refine_model=refine_model,
                         refine_mode=refine_mode, llm_timeout=cfg.llm_timeout)

    return _cli


cli = _build_cli()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _infer_vbook_metadata(input_path: Path) -> tuple[str, str, str]:
    lesson_title = input_path.stem
    series = input_path.parent.name if input_path.parent.name else ""
    course = ""
    if input_path.parent.parent != input_path.parent:
        course = input_path.parent.parent.name
    return course, series, lesson_title


def _manifest_error_code(exc: Exception) -> str:
    if isinstance(exc, ServerConnectionError):
        return "server_connection_error"
    if isinstance(exc, QueueFullError):
        return "queue_full"
    if isinstance(exc, ServerError):
        return "server_error"
    if isinstance(exc, RefineError):
        return "refine_error"
    if isinstance(exc, VtextClientError):
        return "client_error"
    return "unexpected_error"


def _write_vbook_refine_fallback(
    output_dir: Path,
    *,
    raw_txt: str,
    lesson_title: str,
    reason: str,
) -> tuple[Path, Path]:
    """Write contract-complete vBook fallback files when LLM refine is unavailable."""
    clean = to_simplified(raw_txt)
    summary = "\n\n".join(
        [
            f"# {lesson_title}",
            (
                "> vtext refine was unavailable for this run. This fallback file "
                "keeps the vBook bundle contract complete and preserves the raw "
                "transcript evidence for downstream processing."
            ),
            f"> Reason: {reason}",
            "## Transcript",
            clean,
        ]
    )
    clean_path = output_dir / "transcript.clean.txt"
    summary_path = output_dir / "summary.md"
    clean_path.write_text(clean, encoding="utf-8")
    summary_path.write_text(summary, encoding="utf-8")
    return clean_path, summary_path


def _transcribe_vbook_bundle(
    input_path: Path,
    *,
    server: str,
    output_dir: Path,
    fmt: str,
    language: str | None,
    model: str | None,
    simplify: bool = False,
    refine: bool = False,
    ollama_url: str = "http://localhost:11434",
    refine_model: str = "qwen3.5:9b",
    refine_mode: str = "auto",
    llm_timeout: int = 300,
) -> None:
    """Transcribe one file into the vBook stable artifact bundle."""
    started_at = _utc_now()
    started = time.monotonic()
    course, series, lesson_title = _infer_vbook_metadata(input_path)
    outputs: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    models = {"asr": model or "", "refine": refine_model if refine else ""}
    wav_path = None
    upload_path = None

    def write_manifest(status: str) -> None:
        finished_at = _utc_now()
        write_lesson_manifest(
            output_dir,
            source_video=input_path,
            course=course,
            series=series,
            lesson_title=lesson_title,
            language=language,
            status=status,
            outputs=outputs,
            models=models,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(time.monotonic() - started, 3),
        )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"Extracting audio from {input_path.name}...", err=True)
        wav_path = extract_wav(input_path)

        upload_path, encoding = maybe_compress(wav_path)
        if encoding:
            click.echo("Compressing audio (zstd)...", err=True)

        click.echo("Submitting transcription job...", err=True)
        job_id = submit_job(
            server,
            upload_path,
            encoding=encoding,
            language=language,
            fmt=fmt,
            model=model,
        )
        click.echo(f"Job {job_id} queued. Waiting for result...", err=True)

        with click.progressbar(length=100, label="Transcribing", file=sys.stderr) as bar:
            last = 0

            def on_progress(pct: int) -> None:
                nonlocal last
                bar.update(pct - last)
                last = pct

            result = stream_progress(server, job_id, on_progress=on_progress)
            bar.update(100 - last)

        raw_txt = result.text or format_output(result.segments, "txt")
        if simplify:
            raw_txt = to_simplified(raw_txt)
        raw_txt_path = output_dir / "transcript.raw.txt"
        raw_txt_path.write_text(raw_txt, encoding="utf-8")
        outputs["raw_txt"] = raw_txt_path.name

        if fmt != "txt":
            raw_formatted = result.formatted or format_output(result.segments, fmt)
            if simplify:
                raw_formatted = to_simplified(raw_formatted)
            raw_fmt_path = output_dir / f"transcript.raw.{fmt}"
            raw_fmt_path.write_text(raw_formatted, encoding="utf-8")
            outputs[f"raw_{fmt}"] = raw_fmt_path.name

        if refine:
            try:
                click.echo("Refining: correcting + structuring...", err=True)
                clean, summary = refine_text(
                    raw_txt,
                    ollama_url=ollama_url,
                    model=refine_model,
                    server_url=server,
                    mode=refine_mode,
                    timeout=llm_timeout,
                )
                clean_path = output_dir / "transcript.clean.txt"
                summary_path = output_dir / "summary.md"
                clean_path.write_text(clean, encoding="utf-8")
                summary_path.write_text(summary, encoding="utf-8")
                outputs["clean_txt"] = clean_path.name
                outputs["summary_md"] = summary_path.name
                click.echo(f"Saved to {clean_path}", err=True)
                click.echo(f"Saved to {summary_path}", err=True)
            except RefineError as e:
                errors.append(error_entry("refine", _manifest_error_code(e), e))
                clean_path, summary_path = _write_vbook_refine_fallback(
                    output_dir,
                    raw_txt=raw_txt,
                    lesson_title=lesson_title,
                    reason=str(e),
                )
                outputs["clean_txt"] = clean_path.name
                outputs["summary_md"] = summary_path.name
                click.echo(f"Warning: refine skipped: {e}", err=True)
                click.echo(f"Saved fallback to {clean_path}", err=True)
                click.echo(f"Saved fallback to {summary_path}", err=True)

        write_manifest("done")
        click.echo(f"Saved vBook bundle to {output_dir}", err=True)
    except (VtextClientError, OSError) as e:
        errors.append(error_entry("transcription", _manifest_error_code(e), e))
        write_manifest("failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - manifest failure record for CLI boundary
        errors.append(error_entry("transcription", "unexpected_error", e))
        write_manifest("failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)
        if upload_path and upload_path != wav_path:
            upload_path.unlink(missing_ok=True)


def _transcribe_file(
    input_path: Path,
    server: str,
    output: str | None,
    fmt: str,
    language: str | None,
    model: str | None,
    simplify: bool = False,
    refine: bool = False,
    ollama_url: str = "http://localhost:11434",
    refine_model: str = "qwen3.5:9b",
    refine_mode: str = "auto",
    llm_timeout: int = 300,
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
        if simplify:
            text = to_simplified(text)
        output_path = _resolve_output_path(input_path, output, fmt)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
            click.echo(f"Saved to {output_path}", err=True)
        else:
            click.echo(text)

        # Refine: produce <stem>_clean.txt + <stem>_summary.md next to source.
        # Non-fatal: a failure warns and skips; the raw transcript is already saved.
        if refine and output_path is not None:
            try:
                click.echo("Refining: correcting + structuring...", err=True)
                plain = result.text or format_output(result.segments, "txt")
                clean, summary = refine_text(
                    plain,
                    ollama_url=ollama_url,
                    model=refine_model,
                    server_url=server,
                    mode=refine_mode,
                    timeout=llm_timeout,
                )
                clean_path = input_path.parent / f"{input_path.stem}_clean.txt"
                summary_path = input_path.parent / f"{input_path.stem}_summary.md"
                clean_path.write_text(clean, encoding="utf-8")
                summary_path.write_text(summary, encoding="utf-8")
                click.echo(f"Saved to {clean_path}", err=True)
                click.echo(f"Saved to {summary_path}", err=True)
            except RefineError as e:
                click.echo(f"Warning: refine skipped: {e}", err=True)

    except (ServerConnectionError, VtextClientError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        if wav_path:
            wav_path.unlink(missing_ok=True)
        if upload_path and upload_path != wav_path:
            upload_path.unlink(missing_ok=True)


def _refine_only(
    input_path: Path,
    *,
    server: str,
    ollama_url: str,
    model: str,
    mode: str,
    timeout: int,
) -> None:
    """Refine existing .txt file(s) without transcribing."""
    if input_path.is_dir():
        files = [
            f for f in sorted(input_path.rglob("*.txt"))
            if not f.name.endswith("_clean.txt")
        ]
        if not files:
            click.echo(f"No .txt files to refine in {input_path}", err=True)
            return
        click.echo(f"Refining {len(files)} file(s)...", err=True)
        for f in files:
            _refine_one_file(
                f, server=server, ollama_url=ollama_url, model=model,
                mode=mode, timeout=timeout,
            )
        return

    _refine_one_file(
        input_path, server=server, ollama_url=ollama_url, model=model,
        mode=mode, timeout=timeout,
    )


def _refine_one_file(
    txt_path: Path,
    *,
    server: str,
    ollama_url: str,
    model: str,
    mode: str,
    timeout: int,
) -> None:
    """Refine one .txt -> <stem>_clean.txt + <stem>_summary.md next to it."""
    try:
        click.echo(f"Refining {txt_path.name}...", err=True)
        plain = txt_path.read_text(encoding="utf-8")
        clean, summary = refine_text(
            plain,
            ollama_url=ollama_url,
            model=model,
            server_url=server,
            mode=mode,
            timeout=timeout,
        )
        clean_path = txt_path.parent / f"{txt_path.stem}_clean.txt"
        summary_path = txt_path.parent / f"{txt_path.stem}_summary.md"
        clean_path.write_text(clean, encoding="utf-8")
        summary_path.write_text(summary, encoding="utf-8")
        click.echo(f"Saved to {clean_path}", err=True)
        click.echo(f"Saved to {summary_path}", err=True)
    except RefineError as e:
        click.echo(f"Warning: refine skipped for {txt_path.name}: {e}", err=True)


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


def _resolve_output_path(
    input_path: Path, output: str | None, fmt: str
) -> Path | None:
    """Resolve the RAW transcript output path.

    Rules:
    - "-" -> None (stdout)
    - None -> <input.parent>/<stem>_raw.<fmt>  (next to source, marked original)
    - directory -> <dir>/<stem>_raw.<fmt>
    - full file path -> used as-is
    """
    if output == "-":
        return None
    if output is None:
        return input_path.parent / f"{input_path.stem}_raw.{fmt}"

    output_path = Path(output)
    if output_path.is_dir() or (not output_path.suffix and not output_path.exists()):
        return output_path / f"{input_path.stem}_raw.{fmt}"
    return output_path
