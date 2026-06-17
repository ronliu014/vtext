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
@click.option("--config", "config_file", default=None, type=click.Path(),
              help="Path to server TOML config file")
def main(host, port, model, binary, workers, config_file):
    """Start vtext transcription server."""
    from pathlib import Path
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

    app = create_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
