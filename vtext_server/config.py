"""Server configuration with TOML + env var support."""
import multiprocessing
import os
from dataclasses import dataclass, field
from pathlib import Path

from vtext_common.config import CONFIG_DIR, load_toml

_CONFIG_FILE = CONFIG_DIR / "server.toml"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = field(default_factory=multiprocessing.cpu_count)
    queue_max: int = 16
    whisper_binary: str = "whisper-cli"
    model: str = "small"
    threads: int = 4
    models_dir: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "vtext" / "models"
    )
    max_file_size: int = 500 * 1024 * 1024  # 500 MB
    request_timeout: int = 300
    job_ttl: int = 600
    log_dir: Path | None = None
    log_level: str = "INFO"


def load_server_config(config_file: Path | None = None) -> ServerConfig:
    """Build ServerConfig applying: defaults → TOML → env vars.

    CLI args are NOT applied here; the caller (``__main__``) overlays
    them on top of the returned object.
    """
    cfg = ServerConfig()
    toml = load_toml(config_file or _CONFIG_FILE)

    # TOML layer
    if "host" in toml:
        cfg.host = str(toml["host"])
    if "port" in toml:
        cfg.port = int(toml["port"])
    if "workers" in toml:
        cfg.workers = int(toml["workers"])
    if "queue_max" in toml:
        cfg.queue_max = int(toml["queue_max"])
    if "whisper_binary" in toml:
        cfg.whisper_binary = str(toml["whisper_binary"])
    if "model" in toml:
        cfg.model = str(toml["model"])
    if "threads" in toml:
        cfg.threads = int(toml["threads"])
    if "models_dir" in toml:
        cfg.models_dir = Path(toml["models_dir"])
    if "max_file_size" in toml:
        cfg.max_file_size = int(toml["max_file_size"])
    if "request_timeout" in toml:
        cfg.request_timeout = int(toml["request_timeout"])
    if "job_ttl" in toml:
        cfg.job_ttl = int(toml["job_ttl"])
    if "log_dir" in toml:
        cfg.log_dir = Path(toml["log_dir"]).expanduser()
    if "log_level" in toml:
        cfg.log_level = str(toml["log_level"]).upper()

    # Env var layer (overrides TOML)
    if v := os.environ.get("WHISPER_CPP_BIN"):
        cfg.whisper_binary = v
    if v := os.environ.get("WHISPER_CPP_MODEL"):
        cfg.model = v
    if v := os.environ.get("VTEXT_HOST"):
        cfg.host = v
    if v := os.environ.get("VTEXT_PORT"):
        cfg.port = int(v)
    if v := os.environ.get("VTEXT_WORKERS"):
        cfg.workers = int(v)
    if v := os.environ.get("VTEXT_MODELS_DIR"):
        cfg.models_dir = Path(v)
    if v := os.environ.get("VTEXT_LOG_DIR"):
        cfg.log_dir = Path(v).expanduser()
    if v := os.environ.get("VTEXT_LOG_LEVEL"):
        cfg.log_level = v.upper()

    return cfg
