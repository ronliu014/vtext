"""Tests for vtext_common.config and vtext_server.config."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from vtext_common.config import load_toml


class TestLoadToml:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_toml(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_loads_valid_toml(self, tmp_path):
        cfg_file = tmp_path / "test.toml"
        cfg_file.write_text('host = "0.0.0.0"\nport = 9000\n', encoding="utf-8")
        result = load_toml(cfg_file)
        assert result["host"] == "0.0.0.0"
        assert result["port"] == 9000

    def test_loads_nested_toml(self, tmp_path):
        cfg_file = tmp_path / "test.toml"
        cfg_file.write_text('[section]\nkey = "value"\n', encoding="utf-8")
        result = load_toml(cfg_file)
        assert result["section"]["key"] == "value"

    def test_empty_file_returns_empty_dict(self, tmp_path):
        cfg_file = tmp_path / "empty.toml"
        cfg_file.write_text("", encoding="utf-8")
        result = load_toml(cfg_file)
        assert result == {}

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="Python 3.11+ only")
    def test_uses_stdlib_tomllib_on_311(self, tmp_path):
        cfg_file = tmp_path / "test.toml"
        cfg_file.write_text('key = "val"\n', encoding="utf-8")
        # Should not raise on 3.11+
        result = load_toml(cfg_file)
        assert result["key"] == "val"

    def test_raises_on_invalid_toml(self, tmp_path):
        cfg_file = tmp_path / "bad.toml"
        cfg_file.write_text("this is not toml !!!", encoding="utf-8")
        with pytest.raises(Exception):
            load_toml(cfg_file)
