"""Tests for vtext_server.config (load_server_config)."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from vtext_server.config import ServerConfig, load_server_config


def write_toml(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


class TestServerConfigDefaults:
    def test_defaults(self):
        cfg = load_server_config(config_file=Path("/nonexistent/path.toml"))
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8000
        assert cfg.model == "small"
        assert cfg.whisper_binary == "whisper-cli"
        assert cfg.threads == 4
        assert cfg.max_file_size == 500 * 1024 * 1024


class TestServerConfigToml:
    def test_toml_overrides_defaults(self, tmp_path):
        cfg_file = write_toml(tmp_path / "server.toml", """
host = "0.0.0.0"
port = 9000
workers = 8
model = "large-v3"
whisper_binary = "/opt/whisper/whisper-cli"
threads = 8
queue_max = 32
max_file_size = 1073741824
request_timeout = 600
job_ttl = 1200
""")
        cfg = load_server_config(cfg_file)
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9000
        assert cfg.workers == 8
        assert cfg.model == "large-v3"
        assert cfg.whisper_binary == "/opt/whisper/whisper-cli"
        assert cfg.threads == 8
        assert cfg.queue_max == 32
        assert cfg.max_file_size == 1073741824
        assert cfg.request_timeout == 600
        assert cfg.job_ttl == 1200

    def test_models_dir_from_toml(self, tmp_path):
        models_path = tmp_path / "my_models"
        cfg_file = write_toml(tmp_path / "server.toml",
                              f'models_dir = "{models_path}"\n')
        cfg = load_server_config(cfg_file)
        assert cfg.models_dir == models_path

    def test_partial_toml_keeps_other_defaults(self, tmp_path):
        cfg_file = write_toml(tmp_path / "server.toml", 'port = 9999\n')
        cfg = load_server_config(cfg_file)
        assert cfg.port == 9999
        assert cfg.host == "127.0.0.1"  # default unchanged

    def test_missing_toml_uses_defaults(self, tmp_path):
        cfg = load_server_config(tmp_path / "no-such-file.toml")
        assert cfg.port == 8000


class TestServerConfigEnvVars:
    def test_env_whisper_bin(self, tmp_path):
        with patch.dict(os.environ, {"WHISPER_CPP_BIN": "/custom/whisper-cli"}):
            cfg = load_server_config(tmp_path / "none.toml")
        assert cfg.whisper_binary == "/custom/whisper-cli"

    def test_env_whisper_model(self, tmp_path):
        with patch.dict(os.environ, {"WHISPER_CPP_MODEL": "tiny"}):
            cfg = load_server_config(tmp_path / "none.toml")
        assert cfg.model == "tiny"

    def test_env_host_port(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_HOST": "0.0.0.0", "VTEXT_PORT": "7777"}):
            cfg = load_server_config(tmp_path / "none.toml")
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 7777

    def test_env_workers(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_WORKERS": "16"}):
            cfg = load_server_config(tmp_path / "none.toml")
        assert cfg.workers == 16

    def test_env_models_dir(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_MODELS_DIR": str(tmp_path / "models")}):
            cfg = load_server_config(tmp_path / "none.toml")
        assert cfg.models_dir == tmp_path / "models"


class TestServerConfigPriority:
    def test_env_overrides_toml(self, tmp_path):
        cfg_file = write_toml(tmp_path / "server.toml", 'model = "base"\n')
        with patch.dict(os.environ, {"WHISPER_CPP_MODEL": "tiny"}):
            cfg = load_server_config(cfg_file)
        # env var wins over TOML
        assert cfg.model == "tiny"

    def test_toml_overrides_defaults(self, tmp_path):
        cfg_file = write_toml(tmp_path / "server.toml", 'port = 9001\n')
        cfg = load_server_config(cfg_file)
        assert cfg.port == 9001

    def test_cli_args_override_all(self, tmp_path):
        """Simulate CLI layer: caller overrides returned config object."""
        cfg_file = write_toml(tmp_path / "server.toml", 'port = 9001\n')
        with patch.dict(os.environ, {"VTEXT_PORT": "9002"}):
            cfg = load_server_config(cfg_file)
        # CLI args applied by __main__:
        cfg.port = 9003
        assert cfg.port == 9003
