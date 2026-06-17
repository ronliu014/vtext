"""Tests for vtext_client.config (load_client_config)."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from vtext_client.config import ClientConfig, load_client_config


def write_toml(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


class TestClientConfigDefaults:
    def test_defaults(self):
        cfg = load_client_config(config_file=Path("/nonexistent/path.toml"))
        assert cfg.server_url == "http://127.0.0.1:8000"
        assert cfg.default_format == "txt"
        assert cfg.default_language is None
        assert cfg.default_model is None
        assert cfg.default_jobs == 1


class TestClientConfigToml:
    def test_toml_overrides_defaults(self, tmp_path):
        cfg_file = write_toml(tmp_path / "client.toml", """
server_url = "http://192.168.1.10:8000"
default_format = "srt"
default_language = "zh"
default_model = "medium"
default_jobs = 4
""")
        cfg = load_client_config(cfg_file)
        assert cfg.server_url == "http://192.168.1.10:8000"
        assert cfg.default_format == "srt"
        assert cfg.default_language == "zh"
        assert cfg.default_model == "medium"
        assert cfg.default_jobs == 4

    def test_partial_toml(self, tmp_path):
        cfg_file = write_toml(tmp_path / "client.toml",
                              'default_format = "vtt"\n')
        cfg = load_client_config(cfg_file)
        assert cfg.default_format == "vtt"
        assert cfg.server_url == "http://127.0.0.1:8000"  # default

    def test_missing_toml_uses_defaults(self, tmp_path):
        cfg = load_client_config(tmp_path / "no-such-file.toml")
        assert cfg.server_url == "http://127.0.0.1:8000"


class TestClientConfigEnvVars:
    def test_env_server_url(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_SERVER_URL": "http://remote:9000"}):
            cfg = load_client_config(tmp_path / "none.toml")
        assert cfg.server_url == "http://remote:9000"

    def test_env_format(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_FORMAT": "srt"}):
            cfg = load_client_config(tmp_path / "none.toml")
        assert cfg.default_format == "srt"

    def test_env_language(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_LANGUAGE": "ja"}):
            cfg = load_client_config(tmp_path / "none.toml")
        assert cfg.default_language == "ja"

    def test_env_model(self, tmp_path):
        with patch.dict(os.environ, {"VTEXT_MODEL": "large-v3"}):
            cfg = load_client_config(tmp_path / "none.toml")
        assert cfg.default_model == "large-v3"


class TestClientConfigPriority:
    def test_env_overrides_toml(self, tmp_path):
        cfg_file = write_toml(tmp_path / "client.toml",
                              'server_url = "http://toml-server:8000"\n')
        with patch.dict(os.environ, {"VTEXT_SERVER_URL": "http://env-server:8000"}):
            cfg = load_client_config(cfg_file)
        assert cfg.server_url == "http://env-server:8000"

    def test_toml_overrides_defaults(self, tmp_path):
        cfg_file = write_toml(tmp_path / "client.toml",
                              'default_jobs = 3\n')
        cfg = load_client_config(cfg_file)
        assert cfg.default_jobs == 3
