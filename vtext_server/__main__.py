"""vtext server entry point."""
from .app import create_app
from .config import ServerConfig
import uvicorn
import click


@click.command()
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
@click.option("--model", default=None)
@click.option("--binary", default=None)
@click.option("--workers", default=None, type=int)
def main(host, port, model, binary, workers):
    config = ServerConfig()
    if host:
        config.host = host
    if port:
        config.port = port
    if model:
        config.model = model
    if binary:
        config.whisper_binary = binary
    if workers:
        config.workers = workers

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
