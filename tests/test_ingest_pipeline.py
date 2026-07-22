"""Tests for sopx.ingest.pipeline — IngestPipeline."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sopx.cache import CacheManager
from sopx.ingest.pipeline import IngestPipeline, IngestResult, check_dependencies


class TestIngestResult:
    def test_dataclass_fields(self, tmp_path):
        result = IngestResult(
            output_dir=tmp_path,
            srt=tmp_path / "transcript.srt",
            text=tmp_path / "full_text.txt",
            metadata=tmp_path / "metadata.json",
            cached=False,
        )
        assert result.output_dir == tmp_path
        assert result.cached is False


def _make_pipeline_with_mocks(tmp_path, cache=None):
    """Create an IngestPipeline with pre-injected mock adapters.

    The whisper mock writes the SRT file to the output_dir so the pipeline
    can read it back.
    """
    cache = cache or CacheManager(tmp_path / "cache")
    pipeline = IngestPipeline(cache=cache)

    expected_text = "Texto transcrito aqui com varias palavras para testar"

    def _fake_transcribe(audio_path, output_dir):
        srt_path = output_dir / "transcript.srt"
        output_dir.mkdir(parents=True, exist_ok=True)
        srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nTexto transcrito aqui com varias palavras para testar\n",
            encoding="utf-8",
        )
        return srt_path, expected_text

    mock_ffmpeg = MagicMock()
    mock_ffmpeg.extract_audio.return_value = tmp_path / "audio.mp3"
    mock_ffmpeg.get_duration.return_value = 300.0
    pipeline._ffmpeg = mock_ffmpeg

    mock_whisper = MagicMock()
    mock_whisper.transcribe_to_text.side_effect = _fake_transcribe
    pipeline._whisper = mock_whisper

    mock_ytdlp = MagicMock()
    pipeline._ytdlp = mock_ytdlp

    return pipeline, mock_ffmpeg, mock_whisper, mock_ytdlp


class TestIngestPipeline:
    def test_init_default(self):
        pipeline = IngestPipeline()
        assert pipeline.config is not None
        assert pipeline.cache is not None

    def test_init_custom(self, tmp_path):
        config = {"language": "en-US", "whisper": {"model_size": "medium"}}
        cache = CacheManager(tmp_path / "cache")
        pipeline = IngestPipeline(config=config, cache=cache)
        assert pipeline.config["language"] == "en-US"

    def test_ingest_local_file(self, tmp_path):
        pipeline, mock_ffmpeg, mock_whisper, _ = _make_pipeline_with_mocks(tmp_path)

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")

        result = pipeline.ingest(str(video), output_base=tmp_path / "output")

        assert result.output_dir.exists()
        assert result.srt.name == "transcript.srt"
        assert result.text.exists()
        assert result.cached is False

        text_content = result.text.read_text()
        assert "Texto transcrito" in text_content

        meta = json.loads(result.metadata.read_text())
        assert "canonical_id" in meta
        assert "upload_date" in meta
        assert "whisper_model" in meta

    def test_ingest_cache_hit(self, tmp_path):
        pipeline, mock_ffmpeg, mock_whisper, _ = _make_pipeline_with_mocks(tmp_path)

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video content")

        result1 = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert result1.cached is False

        result2 = pipeline.ingest(str(video), output_base=tmp_path / "output")
        assert result2.cached is True
        assert result2.output_dir == result1.output_dir

        mock_ffmpeg.extract_audio.assert_called_once()
        mock_whisper.transcribe_to_text.assert_called_once()

    def test_ingest_file_not_found(self, tmp_path):
        pipeline, _, _, _ = _make_pipeline_with_mocks(tmp_path)

        with pytest.raises(FileNotFoundError, match="não encontrado"):
            pipeline.ingest("/nonexistent/video.mp4")

    def test_ingest_url(self, tmp_path):
        pipeline, mock_ffmpeg, mock_whisper, mock_ytdlp = _make_pipeline_with_mocks(tmp_path)
        mock_ytdlp.get_info.return_value = {
            "canonical_id": "ABC123",
            "title": "Test Video",
            "uploader": "Channel",
            "upload_date": "20250101",
            "duration": 300,
        }
        mock_ytdlp.download_audio.return_value = tmp_path / "audio.mp3"

        result = pipeline.ingest(
            "https://youtube.com/watch?v=abc",
            output_base=tmp_path / "output",
        )
        meta = json.loads(result.metadata.read_text())
        assert meta["canonical_id"] == "ABC123"
        mock_ytdlp.get_info.assert_called_once()
        mock_ytdlp.download_audio.assert_called_once()
        mock_ffmpeg.extract_audio.assert_not_called()

    def test_metadata_schema(self, tmp_path):
        pipeline, _, _, _ = _make_pipeline_with_mocks(tmp_path)

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video")
        result = pipeline.ingest(str(video), output_base=tmp_path / "output")

        meta = json.loads(result.metadata.read_text())
        required_keys = {
            "source", "canonical_id", "title", "uploader", "upload_date",
            "ingested_at", "duration_seconds", "whisper_model", "language",
            "word_count",
        }
        assert required_keys.issubset(meta.keys())

    def test_list_cache(self, tmp_path):
        pipeline, _, _, _ = _make_pipeline_with_mocks(tmp_path)

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        pipeline.ingest(str(video), output_base=tmp_path / "output")

        entries = pipeline.cache.entries()
        assert len(entries) == 1


class TestCheckDependencies:
    def test_returns_dict(self):
        deps = check_dependencies()
        assert isinstance(deps, dict)
        assert "yt-dlp" in deps
        assert "ffmpeg" in deps
        assert "faster-whisper" in deps
        for v in deps.values():
            assert isinstance(v, bool)
