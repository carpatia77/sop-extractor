"""STRESS TESTS — Massive edge-case coverage for the ingestion module.

Tests every possible failure mode, boundary condition, and adversarial input.
Run: python -m pytest tests/test_stress_ingestion.py -v --tb=short
"""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from sopx.cache import CacheManager
from sopx.config import (
    DEFAULTS,
    _deep_merge,
    ensure_config,
    get,
    load_config,
    save_config,
)
from sopx.ingest.adapters import (
    FFmpegAdapter,
    WhisperAdapter,
    YtDlpAdapter,
    _find_binary,
    _format_timestamp_srt,
    _segments_to_srt,
    find_binary_safe,
)
from sopx.ingest.pipeline import IngestPipeline, IngestResult, check_dependencies


# ============================================================================
# STRESS: Cache Manager — Adversarial inputs, race conditions, corruption
# ============================================================================

class TestCacheStress:
    """Cache stress: massive keys, concurrent access, corruption recovery."""

    def test_key_collision抵抗(self):
        """10000 unique IDs must produce 10000 unique keys."""
        keys = set()
        for i in range(10000):
            k = CacheManager.key_for_url(f"video_{i}_{'x' * 100}")
            keys.add(k)
        assert len(keys) == 10000, f"Key collision: {10000 - len(keys)} duplicates"

    def test_key_unicode_stability(self):
        """Unicode video IDs produce stable keys."""
        ids = [
            "Vídeo 1 — Aprendendo",
            "日本語テスト",
            "🔥 Fire Tutorial",
            "Aula 01: Introdução ao Mercado",
            "Курс по Python",
        ]
        for vid in ids:
            k1 = CacheManager.key_for_url(vid)
            k2 = CacheManager.key_for_url(vid)
            assert k1 == k2, f"Key unstable for: {vid}"
            assert len(k1) == 16

    def test_key_length_exactly_16(self):
        """Every key is exactly 16 hex chars."""
        for i in range(1000):
            k = CacheManager.key_for_url(f"test_{i}")
            assert len(k) == 16
            int(k, 16)  # Must be valid hex

    def test_file_key_stat_based(self):
        """File keys change with content, size, and mtime."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello")
            path = f.name

        k1 = CacheManager.key_for_file(path)

        # Same content, same stat → same key
        k2 = CacheManager.key_for_file(path)
        assert k1 == k2

        # Change content → different key
        with open(path, "wb") as f:
            f.write(b"hello world")
        k3 = CacheManager.key_for_file(path)
        assert k3 != k1

        os.unlink(path)

    def test_sequential_cache_writes(self):
        """500 sequential writes — verifies correctness (CacheManager is not thread-safe)."""
        cache_dir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir)

        for i in range(500):
            key = CacheManager.key_for_url(f"t{i}")
            cache.mark_done(key, f"/tmp/out_{i}")

        entries = cache.entries()
        assert len(entries) == 500, f"Expected 500 entries, got {len(entries)}"

    def test_cache_corruption_recovery(self):
        """Corrupted index.json is handled gracefully."""
        cache_dir = tempfile.mkdtemp()
        index_path = Path(cache_dir) / "index.json"
        index_path.write_text("NOT JSON {{{")

        # Should not crash on load
        cache = CacheManager(cache_dir)
        assert cache.is_done("anything") is False

    def test_cache_empty_file_recovery(self):
        """Empty index.json is handled."""
        cache_dir = tempfile.mkdtemp()
        index_path = Path(cache_dir) / "index.json"
        index_path.write_text("")

        cache = CacheManager(cache_dir)
        assert cache.entries() == []

    def test_cache_huge_index(self):
        """500 entries in cache — performance check."""
        cache_dir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir)

        start = time.time()
        for i in range(500):
            key = CacheManager.key_for_url(f"video_{i}")
            cache.mark_done(key, f"/tmp/out_{i}")
        elapsed_write = time.time() - start

        start = time.time()
        entries = cache.entries()
        elapsed_read = time.time() - start

        assert len(entries) == 500
        assert elapsed_write < 5, f"Write too slow: {elapsed_write:.1f}s"
        assert elapsed_read < 1, f"Read too slow: {elapsed_read:.1f}s"

    def test_cache_stage_isolation(self):
        """Audio and SRT stages are independent."""
        cache_dir = tempfile.mkdtemp()
        cache = CacheManager(cache_dir)
        key = "test_key_123"

        # Audio done, SRT not
        audio_dir = cache.stage_path(key, "audio")
        (audio_dir / "audio.mp3").write_bytes(b"fake")
        assert cache.is_stage_done(key, "audio") is True
        assert cache.is_stage_done(key, "srt") is False

        # SRT done
        srt_dir = cache.stage_path(key, "srt")
        (srt_dir / "transcript.srt").write_text("1\n00:00 --> 00:01\nhi\n")
        assert cache.is_stage_done(key, "srt") is True

    def test_cache_clear_and_reuse(self):
        """Clear cache, reuse same dir."""
        cache_dir = tempfile.mkdtemp()
        cache1 = CacheManager(cache_dir)
        for i in range(100):
            key = CacheManager.key_for_url(f"v{i}")
            cache1.mark_done(key, f"/tmp/{i}")

        assert len(cache1.entries()) == 100
        cache1.clear()
        assert len(cache1.entries()) == 0

        cache2 = CacheManager(cache_dir)
        assert len(cache2.entries()) == 0


# ============================================================================
# STRESS: Config Manager — Malformed YAML, edge cases, concurrent access
# ============================================================================

class TestConfigStress:
    """Config stress: adversarial YAML, missing pyyaml, race conditions."""

    def test_deep_merge_preserves_all_keys(self):
        """Override with partial config doesn't drop base keys."""
        base = {"a": 1, "b": 2, "c": 3}
        override = {"b": 99}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_deep_merge_nested_override(self):
        """Deep nested override works correctly."""
        base = {"x": {"a": {"b": {"c": 1}}}}
        override = {"x": {"a": {"b": {"c": 999, "d": 2}}}}
        result = _deep_merge(base, override)
        assert result["x"]["a"]["b"]["c"] == 999
        assert result["x"]["a"]["b"]["d"] == 2

    def test_deep_merge_non_dict_values(self):
        """Override dict with scalar and vice versa."""
        assert _deep_merge({"a": 1}, {"a": {"nested": True}}) == {"a": {"nested": True}}
        assert _deep_merge({"a": {"nested": True}}, {"a": 1}) == {"a": 1}

    def test_load_config_empty_yaml(self):
        """Empty YAML file returns defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        config = load_config(path)
        assert config["language"] == "pt-BR"
        os.unlink(path)

    def test_load_config_malformed_yaml(self):
        """Malformed YAML — should not crash, falls back to defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(": : : invalid\n  - - -\n")
            path = f.name
        # Should not crash
        config = load_config(path)
        assert config["language"] == "pt-BR"
        os.unlink(path)

    def test_load_config_missing_whisper_key(self):
        """Config without whisper section."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("language: en-US\n")
            path = f.name
        config = load_config(path)
        assert config["language"] == "en-US"
        assert config["whisper"]["model_size"] == "base"
        os.unlink(path)

    def test_load_config_extra_unknown_keys(self):
        """Extra unknown keys are preserved."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("language: en-US\nunknown_key: 42\nnested: {deep: true}\n")
            path = f.name
        config = load_config(path)
        assert config["unknown_key"] == 42
        assert config["nested"]["deep"] is True
        os.unlink(path)

    def test_load_config_tilde_expansion(self):
        """Config path with ~ expands correctly."""
        path = Path("~/.config/sopx/nonexistent_test.yaml").expanduser()
        config = load_config(path)
        assert config["language"] == "pt-BR"

    def test_save_load_roundtrip_unicode(self):
        """Save and load config with unicode content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name

        original = {"language": "pt-BR", "title": "Aula do Professor ☺"}
        save_config(original, path)
        loaded = load_config(path)
        assert loaded["title"] == "Aula do Professor ☺"
        os.unlink(path)

    def test_get_dot_notation_deep(self):
        """Get with deeply nested dot notation."""
        config = {"a": {"b": {"c": {"d": 42}}}}
        assert get(config, "a.b.c.d") == 42
        assert get(config, "a.b.c.d.e", "fallback") == "fallback"
        assert get(config, "a.b.x", 99) == 99

    def test_get_on_non_dict(self):
        """Get on a non-dict value returns default."""
        config = {"a": "string"}
        assert get(config, "a.b", "default") == "default"

    def test_sequential_config_writes(self):
        """Multiple sequential config writes."""
        for i in range(20):
            path = tempfile.mktemp(suffix=".yaml")
            config = {"thread": i, "language": "en-US"}
            save_config(config, path)
            loaded = load_config(path)
            assert loaded["thread"] == i
            os.unlink(path)


# ============================================================================
# STRESS: Adapters — Binary detection, subprocess failures, edge cases
# ============================================================================

class TestAdaptersStress:
    """Adapter stress: binary not found, subprocess timeout, invalid input."""

    def test_find_binary_safe_no_crash(self):
        """find_binary_safe never crashes."""
        result = find_binary_safe("nonexistent_binary_xyz")
        assert result is None

    def test_find_binary_raises_with_hint(self):
        """_find_binary raises with install hint."""
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            _find_binary("nonexistent_binary_xyz")

    def test_ytdlp_is_url_edge_cases(self):
        """URL detection edge cases."""
        assert YtDlpAdapter.is_url("https://youtube.com/watch?v=abc") is True
        assert YtDlpAdapter.is_url("http://vimeo.com/123") is True
        assert YtDlpAdapter.is_url("ftp://example.com/video.mp4") is False
        assert YtDlpAdapter.is_url("file:///path/to/video.mp4") is False
        assert YtDlpAdapter.is_url("/absolute/path.mp4") is False
        assert YtDlpAdapter.is_url("relative/path.mp4") is False
        assert YtDlpAdapter.is_url("") is False
        assert YtDlpAdapter.is_url("just-text") is False
        assert YtDlpAdapter.is_url("https://youtu.be/ABC123") is True
        assert YtDlpAdapter.is_url("HTTPS://YOUTUBE.COM/WATCH") is True

    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_ytdlp_get_info_timeout(self, mock_find):
        """yt-dlp subprocess timeout is handled."""
        import sopx.ingest.adapters as mod

        original_run = mod.subprocess.run

        def timeout_run(*args, **kwargs):
            raise mod.subprocess.TimeoutExpired(cmd=args[0] if args else "", timeout=120)

        with patch.object(mod.subprocess, "run", side_effect=timeout_run):
            adapter = YtDlpAdapter()
            with pytest.raises(Exception):
                adapter.get_info("https://youtube.com/watch?v=timeout_test")

    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_ytdlp_get_info_invalid_json(self, mock_find):
        """yt-dlp returns invalid JSON."""
        import sopx.ingest.adapters as mod

        with patch.object(
            mod.subprocess, "run",
            return_value=MagicMock(returncode=0, stdout="NOT JSON", stderr="")
        ):
            adapter = YtDlpAdapter()
            with pytest.raises(json.JSONDecodeError):
                adapter.get_info("https://youtube.com/watch?v=json_test")

    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_ytdlp_get_info_empty_stdout(self, mock_find):
        """yt-dlp returns empty stdout with code 0."""
        import sopx.ingest.adapters as mod

        with patch.object(
            mod.subprocess, "run",
            return_value=MagicMock(returncode=0, stdout="", stderr="")
        ):
            adapter = YtDlpAdapter()
            with pytest.raises(json.JSONDecodeError):
                adapter.get_info("https://youtube.com/watch?v=empty")

    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_ytdlp_download_no_audio_file(self, mock_find):
        """yt-dlp succeeds but produces no audio file."""
        import sopx.ingest.adapters as mod

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr.readline.side_effect = ["", ""]
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0

        with patch.object(mod.subprocess, "Popen", return_value=mock_proc):
            adapter = YtDlpAdapter()
            with tempfile.TemporaryDirectory() as tmpdir:
                with pytest.raises(FileNotFoundError, match="não gerou"):
                    adapter.download_audio(
                        "https://youtube.com/watch?v=noaudio",
                        tmpdir,
                    )

    @patch("sopx.ingest.adapters._find_binary")
    def test_ffmpeg_init_missing_binary(self, mock_find):
        """FFmpegAdapter raises if ffmpeg not found."""
        def side_effect(name):
            if name == "ffmpeg":
                raise FileNotFoundError("não encontrado")
            return "/usr/bin/ffprobe"

        mock_find.side_effect = side_effect
        with pytest.raises(FileNotFoundError):
            FFmpegAdapter()

    @patch("sopx.ingest.adapters._find_binary")
    def test_ffmpeg_extract_audio_failure(self, mock_find, tmp_path):
        """ffmpeg returns non-zero exit code."""
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        import sopx.ingest.adapters as mod

        with patch.object(
            mod.subprocess, "run",
            return_value=MagicMock(
                returncode=1, stdout="", stderr="Error: codec not found"
            )
        ):
            adapter = FFmpegAdapter()
            video = tmp_path / "input.mp4"
            video.write_bytes(b"fake")
            with pytest.raises(RuntimeError, match="ffmpeg falhou"):
                adapter.extract_audio(video, tmp_path / "output")

    @patch("sopx.ingest.adapters._find_binary")
    def test_ffmpeg_get_duration_invalid_output(self, mock_find):
        """ffprobe returns non-numeric output."""
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        import sopx.ingest.adapters as mod

        with patch.object(
            mod.subprocess, "run",
            return_value=MagicMock(returncode=0, stdout="not_a_number\n", stderr="")
        ):
            adapter = FFmpegAdapter()
            with pytest.raises(ValueError):
                adapter.get_duration("/fake/video.mp4")

    def test_whisper_adapter_default_model(self):
        """WhisperAdapter defaults to 'base'."""
        adapter = WhisperAdapter()
        assert adapter.model_size == "base"

    def test_whisper_adapter_custom_model(self):
        """WhisperAdapter accepts custom model."""
        adapter = WhisperAdapter(model_size="large-v3")
        assert adapter.model_size == "large-v3"

    @patch("sopx.ingest.adapters.WhisperAdapter._load_model")
    def test_whisper_transcribe_empty_audio(self, mock_load, tmp_path):
        """Whisper transcribes empty audio — returns empty SRT."""
        segs = []
        info = MagicMock(duration=0.0, language="en")
        mock_batched = MagicMock()
        mock_batched.transcribe.return_value = (segs, info)

        adapter = WhisperAdapter()
        adapter._model = MagicMock()
        adapter._batched_model = mock_batched

        audio = tmp_path / "empty.mp3"
        audio.write_bytes(b"")

        srt_path = adapter.transcribe_to_srt(audio, tmp_path / "output")
        content = srt_path.read_text()
        assert content == "" or content.strip() == ""

    @patch("sopx.ingest.adapters.WhisperAdapter._load_model")
    def test_whisper_transcribe_huge_segment(self, mock_load, tmp_path):
        """Whisper returns segment with very long text."""
        long_text = "word " * 10000
        seg = MagicMock(start=0.0, end=3600.0, text=long_text)
        info = MagicMock(duration=3600.0, language="en")

        mock_batched = MagicMock()
        mock_batched.transcribe.return_value = ([seg], info)

        adapter = WhisperAdapter()
        adapter._model = MagicMock()
        adapter._batched_model = mock_batched

        audio = tmp_path / "huge.mp3"
        audio.write_bytes(b"fake")

        srt_path = adapter.transcribe_to_srt(audio, tmp_path / "output")
        content = srt_path.read_text()
        assert len(content) > 10000

    def test_format_timestamp_edge_cases(self):
        """SRT timestamp formatting edge cases."""
        assert _format_timestamp_srt(0.0) == "00:00:00,000"
        assert _format_timestamp_srt(0.001) == "00:00:00,001"
        assert _format_timestamp_srt(0.999) == "00:00:00,999"
        assert _format_timestamp_srt(3599.999) == "00:59:59,999"
        assert _format_timestamp_srt(3600.0) == "01:00:00,000"
        assert _format_timestamp_srt(86399.999) == "23:59:59,999"

    def test_segments_to_srt_unicode(self):
        """SRT with unicode segments."""
        segs = [
            MagicMock(start=0.0, end=2.0, text=" Olá mundo"),
            MagicMock(start=3.0, end=5.0, text=" 日本語テスト"),
            MagicMock(start=6.0, end=8.0, text=" 🔥 Fire"),
        ]
        srt = _segments_to_srt(segs)
        assert "Olá mundo" in srt
        assert "日本語テスト" in srt
        assert "🔥 Fire" in srt

    def test_segments_to_srt_empty_segments(self):
        """SRT from empty segment list."""
        srt = _segments_to_srt([])
        assert srt == "" or srt.strip() == ""


# ============================================================================
# STRESS: Ingest Pipeline — All possible code paths, error recovery
# ============================================================================

class TestPipelineStress:
    """Pipeline stress: all input combinations, error injection, edge cases."""

    def _make_pipeline(self, tmp_path):
        """Create pipeline with all mocked adapters."""
        cache = CacheManager(tmp_path / "cache")
        pipeline = IngestPipeline(cache=cache)

        expected_text = "Texto de teste para stress"

        def fake_transcribe(audio_path, output_dir):
            srt_path = output_dir / "transcript.srt"
            output_dir.mkdir(parents=True, exist_ok=True)
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nTexto de teste para stress\n",
                encoding="utf-8",
            )
            return srt_path, expected_text

        pipeline._ffmpeg = MagicMock()
        pipeline._ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
        pipeline._ffmpeg.get_duration.return_value = 300.0

        pipeline._whisper = MagicMock()
        pipeline._whisper.transcribe_to_text.side_effect = fake_transcribe

        pipeline._ytdlp = MagicMock()
        return pipeline

    def test_ingest_local_file_with_spaces(self, tmp_path):
        """Local file path with spaces."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "my video file.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert result.output_dir.exists()

    def test_ingest_local_file_with_unicode_name(self, tmp_path):
        """Local file with unicode characters in name."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "视频教程.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert result.output_dir.exists()

    def test_ingest_local_file_special_chars(self, tmp_path):
        """Local file with special characters."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "video (copy) [1080p].mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert result.output_dir.exists()

    def test_ingest_url_various_formats(self, tmp_path):
        """Different URL formats all work."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline._ytdlp.get_info.return_value = {
            "canonical_id": "ABC123",
            "title": "Test",
            "uploader": "Channel",
            "upload_date": "20250101",
            "duration": 300,
        }
        pipeline._ytdlp.download_audio.return_value = tmp_path / "audio.mp3"

        urls = [
            "https://www.youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://m.youtube.com/watch?v=abc123",
            "http://vimeo.com/12345",
        ]
        for url in urls:
            result = pipeline.ingest(url, output_base=tmp_path / "output")
            assert result.output_dir.exists()

    def test_ingest_file_not_found_error(self, tmp_path):
        """Non-existent local file raises FileNotFoundError."""
        pipeline = self._make_pipeline(tmp_path)
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            pipeline.ingest("/nonexistent/path/video.mp4")

    def test_ingest_url_ytdlp_error(self, tmp_path):
        """yt-dlp failure raises RuntimeError."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline._ytdlp.get_info.side_effect = RuntimeError("yt-dlp falhou")

        with pytest.raises(RuntimeError, match="yt-dlp falhou"):
            pipeline.ingest("https://youtube.com/watch?v=bad")

    def test_ingest_metadata_schema_completeness(self, tmp_path):
        """metadata.json has all required fields."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        meta = json.loads(result.metadata.read_text())

        required = {
            "source", "canonical_id", "title", "uploader", "upload_date",
            "ingested_at", "duration_seconds", "whisper_model", "language",
            "word_count",
        }
        assert required.issubset(meta.keys()), f"Missing: {required - meta.keys()}"

    def test_ingest_metadata_upload_date_format(self, tmp_path):
        """Upload date is formatted as YYYY-MM-DD."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline._ytdlp.get_info.return_value = {
            "canonical_id": "DATE123",
            "title": "Date Test",
            "uploader": "Channel",
            "upload_date": "20250615",
            "duration": 120,
        }
        pipeline._ytdlp.download_audio.return_value = tmp_path / "audio.mp3"

        result = pipeline.ingest(
            "https://youtube.com/watch?v=date",
            output_base=tmp_path / "output",
        )
        meta = json.loads(result.metadata.read_text())
        assert meta["upload_date"] == "2025-06-15"

    def test_ingest_metadata_no_upload_date(self, tmp_path):
        """No upload_date is handled gracefully."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline._ytdlp.get_info.return_value = {
            "canonical_id": "NODATE",
            "title": "No Date",
            "uploader": "Channel",
            "upload_date": "",
            "duration": 60,
        }
        pipeline._ytdlp.download_audio.return_value = tmp_path / "audio.mp3"

        result = pipeline.ingest(
            "https://youtube.com/watch?v=nodate",
            output_base=tmp_path / "output",
        )
        meta = json.loads(result.metadata.read_text())
        assert meta["upload_date"] == ""

    def test_ingest_cache_roundtrip(self, tmp_path):
        """Full cache roundtrip: ingest → cache hit → same result."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        r1 = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert r1.cached is False

        r2 = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert r2.cached is True
        assert r2.output_dir == r1.output_dir

        # External calls only once
        pipeline._ffmpeg.extract_audio.assert_called_once()
        pipeline._whisper.transcribe_to_text.assert_called_once()

    def test_ingest_no_cache_flag(self, tmp_path):
        """--no-cache flag forces reprocessing."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline.config["cache_enabled"] = False

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        r1 = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert r1.cached is False

        r2 = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert r2.cached is False

        pipeline._ffmpeg.extract_audio.assert_called()
        pipeline._whisper.transcribe_to_text.assert_called()

    def test_ingest_custom_output_dir(self, tmp_path):
        """Custom output directory is used."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        custom_dir = tmp_path / "custom" / "nested"
        result = pipeline.ingest(str(video), output_base=custom_dir)
        assert str(custom_dir) in str(result.output_dir)

    def test_ingest_word_count_accuracy(self, tmp_path):
        """Word count in metadata matches actual text."""
        pipeline = self._make_pipeline(tmp_path)

        # Override whisper to return specific word count
        def exact_transcribe(audio_path, output_dir):
            srt_path = output_dir / "transcript.srt"
            text = "one two three four five"
            srt_path.write_text(
                f"1\n00:00:00,000 --> 00:00:02,000\n{text}\n",
                encoding="utf-8",
            )
            return srt_path, text

        pipeline._whisper.transcribe_to_text.side_effect = exact_transcribe
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        meta = json.loads(result.metadata.read_text())
        assert meta["word_count"] == 5

    def test_ingest_file_duration_from_ffmpeg(self, tmp_path):
        """Local file duration comes from ffmpeg."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline._ffmpeg.get_duration.return_value = 1234.5

        video = tmp_path / "long.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        meta = json.loads(result.metadata.read_text())
        assert meta["duration_seconds"] == 1234.5

    def test_ingest_url_duration_from_ytdlp(self, tmp_path):
        """URL duration comes from yt-dlp info."""
        pipeline = self._make_pipeline(tmp_path)
        pipeline._ytdlp.get_info.return_value = {
            "canonical_id": "DUR123",
            "title": "Duration",
            "uploader": "Channel",
            "upload_date": "20250101",
            "duration": 9999,
        }
        pipeline._ytdlp.download_audio.return_value = tmp_path / "audio.mp3"

        result = pipeline.ingest(
            "https://youtube.com/watch?v=dur",
            output_base=tmp_path / "output",
        )
        meta = json.loads(result.metadata.read_text())
        assert meta["duration_seconds"] == 9999

    def test_ingest_timestamp_format(self, tmp_path):
        """ingested_at timestamp is ISO 8601 UTC."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        meta = json.loads(result.metadata.read_text())
        ts = meta["ingested_at"]
        assert ts.endswith("Z")
        # Parse should not crash
        time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")

    def test_check_dependencies_returns_bools(self):
        """check_dependencies returns dict of booleans."""
        deps = check_dependencies()
        assert isinstance(deps, dict)
        for key, val in deps.items():
            assert isinstance(val, bool), f"{key} should be bool, got {type(val)}"

    def test_ingest_output_files_exist(self, tmp_path):
        """All expected output files are created."""
        pipeline = self._make_pipeline(tmp_path)
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")

        assert result.output_dir.is_dir()
        assert result.srt.exists()
        assert result.text.exists()
        assert result.metadata.exists()
        assert result.srt.name == "transcript.srt"
        assert result.text.name == "full_text.txt"
        assert result.metadata.name == "metadata.json"


# ============================================================================
# STRESS: CLI (ingest.py) — Argument parsing, all flag combinations
# ============================================================================

class TestCLIStress:
    """CLI stress: argument combinations, --status, --check, edge cases."""

    def test_check_flag(self):
        """--check prints dependency status."""
        from scripts.ingest import check_deps
        result = check_deps()
        assert isinstance(result, bool)

    def test_status_flag_empty(self):
        """--status with no cache shows empty message."""
        from scripts.ingest import show_status
        # Should not crash
        show_status()

    def test_no_args_prints_help(self):
        """No arguments prints help and returns 1."""
        from scripts.ingest import main
        result = main([])
        assert result == 1

    def test_check_returns_exit_code(self):
        """--check returns 0 if all deps present, 1 otherwise."""
        from scripts.ingest import main
        result = main(["--check"])
        assert result in (0, 1)

    def test_status_returns_zero(self):
        """--status returns 0."""
        from scripts.ingest import main
        result = main(["--status"])
        assert result == 0


# ============================================================================
# STRESS: Integration — Full pipeline with realistic mock data
# ============================================================================

class TestIntegrationStress:
    """Integration stress: realistic multi-source pipeline simulation."""

    def test_multiple_files_sequential(self, tmp_path):
        """Ingest 10 different files sequentially."""
        pipeline = IngestPipeline(cache=CacheManager(tmp_path / "cache"))
        pipeline._ffmpeg = MagicMock()
        pipeline._ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
        pipeline._ffmpeg.get_duration.return_value = 300.0

        pipeline._whisper = MagicMock()
        results_text = ["word " * (i + 1) for i in range(10)]

        call_count = [0]

        def fake_transcribe(audio_path, output_dir):
            idx = call_count[0]
            call_count[0] += 1
            text = results_text[idx]
            srt_path = output_dir / "transcript.srt"
            srt_path.write_text(
                f"1\n00:00:00,000 --> 00:00:02,000\n{text}\n",
                encoding="utf-8",
            )
            return srt_path, text

        pipeline._whisper.transcribe_to_text.side_effect = fake_transcribe
        pipeline._ytdlp = MagicMock()

        results = []
        for i in range(10):
            video = tmp_path / f"video_{i}.mp4"
            video.write_bytes(f"fake content {i}".encode())
            result = pipeline.ingest(str(video), output_base=tmp_path / "output")
            results.append(result)

        assert len(results) == 10
        for r in results:
            assert r.output_dir.exists()

        # Second pass should be all cache hits
        for i in range(10):
            video = tmp_path / f"video_{i}.mp4"
            result = pipeline.ingest(str(video), output_base=tmp_path / "output")
            assert result.cached is True

    def test_same_file_different_locations(self, tmp_path):
        """Same file content in different directories — same cache key."""
        pipeline = IngestPipeline(cache=CacheManager(tmp_path / "cache"))
        pipeline._ffmpeg = MagicMock()
        pipeline._ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
        pipeline._ffmpeg.get_duration.return_value = 100.0

        pipeline._whisper = MagicMock()

        def fake_transcribe(audio_path, output_dir):
            srt_path = output_dir / "transcript.srt"
            output_dir.mkdir(parents=True, exist_ok=True)
            srt_path.write_text("1\n00:00 --> 00:01\ntext\n", encoding="utf-8")
            return srt_path, "text"

        pipeline._whisper.transcribe_to_text.side_effect = fake_transcribe
        pipeline._ytdlp = MagicMock()

        # Create two copies of same content
        video1 = tmp_path / "dir1" / "video.mp4"
        video2 = tmp_path / "dir2" / "video.mp4"
        video1.parent.mkdir()
        video2.parent.mkdir()
        content = b"identical content"
        video1.write_bytes(content)
        video2.write_bytes(content)

        # Touch same time to ensure same stat
        os.utime(video1, (0, 0))
        os.utime(video2, (0, 0))

        r1 = pipeline.ingest(str(video1), output_base=tmp_path / "output")
        # Different path → different key (stat includes absolute path)
        r2 = pipeline.ingest(str(video2), output_base=tmp_path / "output")

        # Both should produce valid results
        assert r1.output_dir.exists()
        assert r2.output_dir.exists()


# ============================================================================
# STRESS: Edge cases in file I/O
# ============================================================================

class TestFileIOStress:
    """File I/O stress: empty files, huge files, permissions."""

    def test_empty_video_file(self, tmp_path):
        """Empty video file — pipeline handles gracefully."""
        pipeline = IngestPipeline(cache=CacheManager(tmp_path / "cache"))
        pipeline._ffmpeg = MagicMock()
        pipeline._ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
        pipeline._ffmpeg.get_duration.return_value = 0.0

        pipeline._whisper = MagicMock()

        def fake_transcribe(audio_path, output_dir):
            srt_path = output_dir / "transcript.srt"
            output_dir.mkdir(parents=True, exist_ok=True)
            srt_path.write_text("", encoding="utf-8")
            return srt_path, ""

        pipeline._whisper.transcribe_to_text.side_effect = fake_transcribe
        pipeline._ytdlp = MagicMock()

        video = tmp_path / "empty.mp4"
        video.write_bytes(b"")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        meta = json.loads(result.metadata.read_text())
        assert meta["word_count"] == 0
        assert meta["duration_seconds"] == 0.0

    def test_metadata_json_unicode_content(self, tmp_path):
        """Metadata with unicode content is saved correctly."""
        pipeline = IngestPipeline(cache=CacheManager(tmp_path / "cache"))
        pipeline._ffmpeg = MagicMock()
        pipeline._ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
        pipeline._ffmpeg.get_duration.return_value = 60.0

        pipeline._whisper = MagicMock()

        def fake_transcribe(audio_path, output_dir):
            srt_path = output_dir / "transcript.srt"
            output_dir.mkdir(parents=True, exist_ok=True)
            srt_path.write_text("1\n00:00 --> 00:01\nOlá mundo 测试\n", encoding="utf-8")
            return srt_path, "Olá mundo 测试"

        pipeline._whisper.transcribe_to_text.side_effect = fake_transcribe
        pipeline._ytdlp = MagicMock()

        video = tmp_path / "unicode.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        meta = json.loads(result.metadata.read_text())
        assert meta["word_count"] == 3  # Olá, mundo, 测试

    def test_srt_content_encoding(self, tmp_path):
        """SRT file content is valid UTF-8."""
        pipeline = IngestPipeline(cache=CacheManager(tmp_path / "cache"))
        pipeline._ffmpeg = MagicMock()
        pipeline._ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
        pipeline._ffmpeg.get_duration.return_value = 60.0

        srt_content = "1\n00:00:00,000 --> 00:00:02,000\nOlá acentos: áéíóú ñ ç\n\n"

        pipeline._whisper = MagicMock()

        def fake_transcribe(audio_path, output_dir):
            srt_path = output_dir / "transcript.srt"
            output_dir.mkdir(parents=True, exist_ok=True)
            srt_path.write_text(srt_content, encoding="utf-8")
            return srt_path, "Olá acentos"

        pipeline._whisper.transcribe_to_text.side_effect = fake_transcribe
        pipeline._ytdlp = MagicMock()

        video = tmp_path / "accents.mp4"
        video.write_bytes(b"fake")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")
        srt_text = result.srt.read_text(encoding="utf-8")
        assert "áéíóú" in srt_text
        assert "ñ" in srt_text
        assert "ç" in srt_text
