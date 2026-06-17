"""Tests for vtext_server.models."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from vtext_server.errors import ModelNotFoundError
from vtext_server.models import (
    resolve_model_path, list_available, list_cached, download,
    MODEL_FILES, MODEL_SIZES_MB,
)
from vtext_server.config import ServerConfig


def make_config(models_dir: Path) -> ServerConfig:
    cfg = ServerConfig()
    cfg.models_dir = models_dir
    return cfg


class TestResolveModelPath:
    def test_absolute_path_exists(self, tmp_path):
        model_file = tmp_path / "custom.bin"
        model_file.touch()
        cfg = make_config(tmp_path)
        result = resolve_model_path(str(model_file), cfg)
        assert result == model_file

    def test_absolute_path_missing_raises(self, tmp_path):
        missing = tmp_path / "missing.bin"
        cfg = make_config(tmp_path)
        with pytest.raises(ModelNotFoundError, match="not found"):
            resolve_model_path(str(missing), cfg)

    def test_named_model_found(self, tmp_path):
        (tmp_path / "ggml-tiny.bin").touch()
        cfg = make_config(tmp_path)
        result = resolve_model_path("tiny", cfg)
        assert result == tmp_path / "ggml-tiny.bin"

    def test_named_model_missing_raises(self, tmp_path):
        cfg = make_config(tmp_path)
        with pytest.raises(ModelNotFoundError, match="tiny"):
            resolve_model_path("tiny", cfg)

    def test_unknown_model_name_raises(self, tmp_path):
        cfg = make_config(tmp_path)
        with pytest.raises(ModelNotFoundError, match="Unknown"):
            resolve_model_path("nonexistent-model", cfg)


class TestListAvailable:
    def test_returns_all_known_models(self):
        available = list_available()
        assert "tiny" in available
        assert "base" in available
        assert "large-v3" in available
        assert set(available) == set(MODEL_FILES.keys())


class TestListCached:
    def test_empty_when_no_files(self, tmp_path):
        cfg = make_config(tmp_path)
        assert list_cached(cfg) == []

    def test_detects_existing_files(self, tmp_path):
        (tmp_path / "ggml-tiny.bin").touch()
        (tmp_path / "ggml-base.bin").touch()
        cfg = make_config(tmp_path)
        cached = list_cached(cfg)
        assert "tiny" in cached
        assert "base" in cached
        assert "large-v3" not in cached


class TestDownload:
    def test_unknown_model_raises(self, tmp_path):
        cfg = make_config(tmp_path)
        with pytest.raises(ModelNotFoundError, match="Unknown"):
            download("nonexistent", cfg)

    def test_already_exists_skips_download(self, tmp_path):
        existing = tmp_path / "ggml-tiny.bin"
        existing.touch()
        cfg = make_config(tmp_path)
        with patch("urllib.request.urlretrieve") as mock_dl:
            result = download("tiny", cfg)
            mock_dl.assert_not_called()
        assert result == existing

    def test_downloads_to_models_dir(self, tmp_path):
        cfg = make_config(tmp_path / "models")  # doesn't exist yet
        with patch("urllib.request.urlretrieve") as mock_dl:
            mock_dl.side_effect = lambda url, dest: Path(dest).touch()
            result = download("tiny", cfg)
            mock_dl.assert_called_once()
            assert result == cfg.models_dir / "ggml-tiny.bin"
        assert cfg.models_dir.exists()
