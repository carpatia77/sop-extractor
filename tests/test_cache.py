"""Tests for sopx.cache — Cache Manager."""
import json
from pathlib import Path

import pytest

from sopx.cache import CacheManager


class TestCacheManager:
    def test_init_creates_directory(self, tmp_path):
        cache_dir = tmp_path / "cache"
        CacheManager(cache_dir)
        assert cache_dir.exists()

    def test_init_loads_existing_index(self, tmp_path):
        cache_dir = tmp_path / "cache"
        index_path = cache_dir / "index.json"
        cache_dir.mkdir()
        index_path.write_text('{"abc123": {"output_dir": "/tmp/out"}}')
        cache = CacheManager(cache_dir)
        assert cache.is_done("abc123")

    def test_key_for_url_deterministic(self):
        k1 = CacheManager.key_for_url("ABC123")
        k2 = CacheManager.key_for_url("ABC123")
        assert k1 == k2

    def test_key_for_url_different_ids(self):
        k1 = CacheManager.key_for_url("ABC123")
        k2 = CacheManager.key_for_url("XYZ789")
        assert k1 != k2

    def test_key_for_url_length(self):
        k = CacheManager.key_for_url("test")
        assert len(k) == 16

    def test_key_for_file_deterministic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        k1 = CacheManager.key_for_file(f)
        k2 = CacheManager.key_for_file(f)
        assert k1 == k2

    def test_key_for_file_different_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert CacheManager.key_for_file(f1) != CacheManager.key_for_file(f2)

    def test_key_for_file_uses_stat(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        k1 = CacheManager.key_for_file(f)
        # Modify content (changes size and mtime)
        f.write_text("hello world!")
        k2 = CacheManager.key_for_file(f)
        assert k1 != k2

    def test_is_done_false(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        assert cache.is_done("nonexistent") is False

    def test_mark_done_and_check(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k = CacheManager.key_for_url("vid123")
        assert cache.is_done(k) is False

        cache.mark_done(k, "/tmp/output", canonical_id="vid123")
        assert cache.is_done(k) is True

    def test_get_output_dir(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k = CacheManager.key_for_url("test")
        cache.mark_done(k, "/tmp/output")
        assert cache.get_output_dir(k) == "/tmp/output"

    def test_entries(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k1 = CacheManager.key_for_url("url1")
        k2 = CacheManager.key_for_url("url2")
        cache.mark_done(k1, "/tmp/out1", canonical_id="url1")
        cache.mark_done(k2, "/tmp/out2", canonical_id="url2")

        entries = cache.entries()
        assert len(entries) == 2

    def test_stage_path(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k = CacheManager.key_for_url("test")
        audio_dir = cache.stage_path(k, "audio")
        assert audio_dir.exists()
        assert audio_dir.name == "audio"

    def test_is_stage_done_false(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k = CacheManager.key_for_url("test")
        assert cache.is_stage_done(k, "audio") is False

    def test_is_stage_done_true(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k = CacheManager.key_for_url("test")
        stage_dir = cache.stage_path(k, "audio")
        (stage_dir / "audio.mp3").write_bytes(b"fake")
        assert cache.is_stage_done(k, "audio") is True

    def test_clear(self, tmp_path):
        cache = CacheManager(tmp_path / "cache")
        k = CacheManager.key_for_url("test")
        cache.mark_done(k, "/tmp/output")
        count = cache.clear()
        assert count == 1
        assert cache.is_done(k) is False

    def test_persistence(self, tmp_path):
        cache_dir = tmp_path / "cache"
        k = CacheManager.key_for_url("test")

        cache1 = CacheManager(cache_dir)
        cache1.mark_done(k, "/tmp/output")

        cache2 = CacheManager(cache_dir)
        assert cache2.is_done(k) is True
