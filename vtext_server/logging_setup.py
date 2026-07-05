"""Logging configuration for vtext-server.

Supports two handlers:
- Console (stderr): always enabled, shows INFO+
- File (TimedRotatingFileHandler): enabled when log_dir is set,
  rotates daily, retains 30 days, filenames like vtext-server.2026-06-17.log
"""
import logging
import logging.handlers
import sys
from pathlib import Path


_FORMATTER = logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def setup_logging(log_dir: Path | None, log_level: str = "INFO") -> None:
    """Configure root logger.  Call once at process start."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any handlers added by uvicorn/fastapi before we run
    root.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_FORMATTER)
    console.setLevel(level)
    root.addHandler(console)

    # File handler (optional)
    if log_dir:
        log_dir = Path(log_dir).expanduser().resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "vtext-server.log"
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
            utc=False,
        )
        # Rename rotated files to vtext-server.YYYY-MM-DD.log
        file_handler.suffix = "%Y-%m-%d.log"
        file_handler.setFormatter(_FORMATTER)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
