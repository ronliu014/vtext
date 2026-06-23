"""vtext server entry point."""
import click
import uvicorn

from .app import create_app
from .config import load_server_config


@click.command()
@click.option("--host", default=None, help="Bind host (overrides config)")
@click.option("--port", default=None, type=int, help="Bind port (overrides config)")
@click.option("--model", default=None, help="Model name or path (overrides config)")
@click.option("--binary", default=None, help="whisper.cpp binary path (overrides config)")
@click.option("--workers", default=None, type=int, help="Worker processes (overrides config)")
@click.option("--ollama-url", default=None,
              help="Ollama URL for the LLM relay (overrides config)")
@click.option("--llm-workers", default=None, type=int,
              help="LLM relay worker processes (overrides config; default 1 = serialized FIFO)")
@click.option("--config", "config_file", default=None, type=click.Path(),
              help="Path to server TOML config file")
@click.option("--log-dir", default=None, type=click.Path(),
              help="Directory for log files (rotated daily). Omit to log to console only.")
@click.option("--log-level", default=None,
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
              help="Log level (overrides config)")
def main(host, port, model, binary, workers, ollama_url, llm_workers,
         config_file, log_dir, log_level):
    """Start vtext transcription server."""
    from pathlib import Path
    from .logging_setup import setup_logging

    cfg = load_server_config(Path(config_file) if config_file else None)

    # CLI args override everything
    if host is not None:
        cfg.host = host
    if port is not None:
        cfg.port = port
    if model is not None:
        cfg.model = model
    if binary is not None:
        cfg.whisper_binary = binary
    if workers is not None:
        cfg.workers = workers
    if ollama_url is not None:
        cfg.ollama_url = ollama_url
    if llm_workers is not None:
        cfg.llm_workers = llm_workers
    if log_dir is not None:
        cfg.log_dir = Path(log_dir)
    if log_level is not None:
        cfg.log_level = log_level.upper()

    setup_logging(cfg.log_dir, cfg.log_level)

    import logging
    logger = logging.getLogger("vtext.server")
    logger.info(
        "starting vtext-server host=%s port=%d workers=%d model=%s "
        "llm_workers=%d ollama_url=%s log_dir=%s",
        cfg.host, cfg.port, cfg.workers, cfg.model, cfg.llm_workers, cfg.ollama_url,
        str(cfg.log_dir) if cfg.log_dir else "console-only",
    )

    app = create_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_config=None)


if __name__ == "__main__":
    main()
