"""Tests for sopx.config — Config Manager."""
import tempfile
from pathlib import Path

import pytest

from sopx.config import (
    DEFAULTS,
    _deep_merge,
    ensure_config,
    get,
    load_config,
    save_config,
)


class TestDeepMerge:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"whisper": {"model_size": "base"}}
        override = {"whisper": {"model_size": "medium"}}
        result = _deep_merge(base, override)
        assert result["whisper"]["model_size"] == "medium"

    def test_empty_override(self):
        base = {"a": 1}
        result = _deep_merge(base, {})
        assert result == {"a": 1}

    def test_empty_base(self):
        override = {"a": 1}
        result = _deep_merge({}, override)
        assert result == {"a": 1}


class TestLoadConfig:
    def test_load_defaults_when_no_file(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config = load_config(config_path)
        assert config["language"] == "pt-BR"
        assert config["cache_enabled"] is True
        assert config["whisper"]["model_size"] == "base"

    def test_load_existing_file(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "language: en-US\nwhisper:\n  model_size: medium\n"
        )
        config = load_config(config_path)
        assert config["language"] == "en-US"
        assert config["whisper"]["model_size"] == "medium"
        assert config["cache_enabled"] is True  # default preserved

    def test_flat_structure(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("language: en-US\n")
        config = load_config(config_path)
        # Flat structure — no nested 'defaults' key
        assert "defaults" not in config
        assert config["language"] == "en-US"


class TestSaveConfig:
    def test_creates_directory(self, tmp_path):
        config_path = tmp_path / "nested" / "dir" / "config.yaml"
        save_config(DEFAULTS, config_path)
        assert config_path.exists()

    def test_roundtrip(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        original = {"language": "en-US", "cache_enabled": True}
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert loaded["language"] == "en-US"


class TestEnsureConfig:
    def test_creates_file_if_missing(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        assert not config_path.exists()
        config = ensure_config(config_path)
        assert config_path.exists()
        assert config["language"] == "pt-BR"

    def test_loads_existing_file(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("language: en-US\n")
        config = ensure_config(config_path)
        assert config["language"] == "en-US"


class TestGet:
    def test_simple_key(self):
        config = {"language": "pt-BR"}
        assert get(config, "language") == "pt-BR"

    def test_nested_key(self):
        config = {"whisper": {"model_size": "base"}}
        assert get(config, "whisper.model_size") == "base"

    def test_missing_key_returns_default(self):
        config = {}
        assert get(config, "missing", "fallback") == "fallback"

    def test_missing_nested_returns_default(self):
        config = {"whisper": {}}
        assert get(config, "whisper.missing", "fallback") == "fallback"
