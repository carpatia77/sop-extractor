"""Tests for sopx.ingest.pipeline — IngestPipeline including batch playlist.

Tests: ingest_playlist with mocked yt-dlp, error handling, max_videos limit.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sopx.ingest.pipeline import IngestPipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pipeline():
    """Create a real IngestPipeline with mocked adapters."""
    with patch("sopx.ingest.pipeline.YtDlpAdapter") as mock_ytdlp, \
         patch("sopx.ingest.pipeline.FFmpegAdapter") as mock_ffmpeg, \
         patch("sopx.ingest.pipeline.WhisperAdapter") as mock_whisper, \
         patch("sopx.ingest.pipeline.CacheManager"):
        p = IngestPipeline.__new__(IngestPipeline)
        p._ytdlp = mock_ytdlp
        p._ytdlp.binary = "/usr/bin/yt-dlp"
        p._ffmpeg = mock_ffmpeg
        p._whisper = mock_whisper
        p.config = {"output_dir": "/tmp/test"}
        yield p


@pytest.fixture
def sample_playlist_output():
    """Sample yt-dlp --flat-playlist --dump-json output."""
    videos = [
        {"id": "video1", "title": "Video 1"},
        {"id": "video2", "title": "Video 2"},
        {"id": "video3", "title": "Video 3"},
    ]
    return "\n".join(json.dumps(v) for v in videos)


# ---------------------------------------------------------------------------
# ingest_playlist
# ---------------------------------------------------------------------------

class TestIngestPlaylist:
    @patch("subprocess.run")
    def test_lists_videos(self, mock_run, pipeline, sample_playlist_output, tmp_path):
        """Playlist lists videos via yt-dlp."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=sample_playlist_output, stderr=""
        )
        pipeline.ingest = MagicMock(return_value=MagicMock(success=True))

        pipeline.ingest_playlist(
            "https://youtube.com/playlist?list=XYZ",
            output_base=str(tmp_path),
        )

        # yt-dlp was called to list videos
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "--flat-playlist" in call_args[0][0]
        assert "--dump-json" in call_args[0][0]

    @patch("subprocess.run")
    def test_max_videos_limit(self, mock_run, pipeline, sample_playlist_output, tmp_path):
        """max_videos limits processing."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=sample_playlist_output, stderr=""
        )
        pipeline.ingest = MagicMock(return_value=MagicMock(success=True))

        pipeline.ingest_playlist(
            "https://youtube.com/playlist?list=XYZ",
            output_base=str(tmp_path),
            max_videos=2,
        )

        # Only 2 videos processed
        assert pipeline.ingest.call_count == 2

    @patch("subprocess.run")
    def test_processes_each_video(self, mock_run, pipeline, sample_playlist_output, tmp_path):
        """Each video is processed via ingest()."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=sample_playlist_output, stderr=""
        )
        pipeline.ingest = MagicMock(return_value=MagicMock(success=True))

        pipeline.ingest_playlist(
            "https://youtube.com/playlist?list=XYZ",
            output_base=str(tmp_path),
        )

        assert pipeline.ingest.call_count == 3
        urls = [call[0][0] for call in pipeline.ingest.call_args_list]
        assert "video1" in urls[0]
        assert "video2" in urls[1]
        assert "video3" in urls[2]

    @patch("subprocess.run")
    def test_handles_video_failure(self, mock_run, pipeline, sample_playlist_output, tmp_path):
        """Failed videos are skipped, not fatal."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=sample_playlist_output, stderr=""
        )
        pipeline.ingest = MagicMock(side_effect=[
            RuntimeError("download failed"),
            MagicMock(success=True),
            MagicMock(success=True),
        ])

        results = pipeline.ingest_playlist(
            "https://youtube.com/playlist?list=XYZ",
            output_base=str(tmp_path),
        )

        assert len(results) == 2

    @patch("subprocess.run")
    def test_empty_playlist(self, mock_run, pipeline, tmp_path):
        """Empty playlist returns empty results."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        results = pipeline.ingest_playlist(
            "https://youtube.com/playlist?list=XYZ",
            output_base=str(tmp_path),
        )

        assert results == []

    @patch("subprocess.run")
    def test_ytdlp_failure_raises(self, mock_run, pipeline, tmp_path):
        """yt-dlp failure raises RuntimeError."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="playlist not found"
        )

        with pytest.raises(RuntimeError, match="yt-dlp falhou"):
            pipeline.ingest_playlist(
                "https://youtube.com/playlist?list=XYZ",
                output_base=str(tmp_path),
            )
