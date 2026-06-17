"""Server configuration."""
import multiprocessing
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = field(default_factory=multiprocessing.cpu_count)
    queue_max: int = 16

    whisper_binary: str = field(
        default_factory=lambda: os.environ.get("WHISPER_CPP_BIN", "whisper-cli")
    )
    model: str = field(
        default_factory=lambda: os.environ.get("WHISPER_CPP_MODEL", "base")
    )
    threads: int = 4
    models_dir: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "vtext" / "models"
    )

    # Resource limits
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    request_timeout: int = 300              # 5 minutes
    job_ttl: int = 600                      # completed jobs kept for 10 minutes
