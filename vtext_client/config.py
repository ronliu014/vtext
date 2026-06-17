"""Client configuration with TOML + env var support."""
import os
from dataclasses import dataclass
from pathlib import Path

from vtext_common.config import CONFIG_DIR, load_toml

_CONFIG_FILE = CONFIG_DIR / "client.toml"


@dataclass
class ClientConfig:
    server_url: str = "http://127.0.0.1:8000"
    default_format: str = "txt"
    default_language: str | None = None
    default_model: str | None = None
    default_jobs: int = 1


def load_client_config(config_file: Path | None = None) -> ClientConfig:
    """Build ClientConfig applying: defaults → TOML → env vars."""
    cfg = ClientConfig()
    toml = load_toml(config_file or _CONFIG_FILE)

    # TOML layer
    if "server_url" in toml:
        cfg.server_url = str(toml["server_url"])
    if "default_format" in toml:
        cfg.default_format = str(toml["default_format"])
    if "default_language" in toml:
        cfg.default_language = str(toml["default_language"])
    if "default_model" in toml:
        cfg.default_model = str(toml["default_model"])
    if "default_jobs" in toml:
        cfg.default_jobs = int(toml["default_jobs"])

    # Env var layer
    if v := os.environ.get("VTEXT_SERVER_URL"):
        cfg.server_url = v
    if v := os.environ.get("VTEXT_FORMAT"):
        cfg.default_format = v
    if v := os.environ.get("VTEXT_LANGUAGE"):
        cfg.default_language = v
    if v := os.environ.get("VTEXT_MODEL"):
        cfg.default_model = v

    return cfg
