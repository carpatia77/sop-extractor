"""Tests for sopx.ingest.adapters — YtDlpAdapter, FFmpegAdapter, WhisperAdapter."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sopx.ingest.adapters import (
    FFmpegAdapter,
    WhisperAdapter,
    YtDlpAdapter,
    _find_binary,
    find_binary_safe,
)


class TestFindBinary:
    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_found(self, mock_which):
        assert _find_binary("ffmpeg") == "/usr/bin/ffmpeg"

    @patch("shutil.which", return_value=None)
    def test_not_found_raises(self, mock_which):
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            _find_binary("ffmpeg")


class TestFindBinarySafe:
    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_found(self, mock_which):
        assert find_binary_safe("ffmpeg") == "/usr/bin/ffmpeg"

    @patch("shutil.which", return_value=None)
    def test_not_found_returns_none(self, mock_which):
        assert find_binary_safe("ffmpeg") is None


class TestYtDlpAdapter:
    def test_is_url(self):
        assert YtDlpAdapter.is_url("https://youtube.com/watch?v=abc") is True
        assert YtDlpAdapter.is_url("http://vimeo.com/123") is True
        assert YtDlpAdapter.is_url("/path/to/video.mp4") is False
        assert YtDlpAdapter.is_url("video.mp4") is False

    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_init_finds_binary(self, mock_find):
        adapter = YtDlpAdapter()
        assert adapter.binary == "/usr/bin/yt-dlp"

    @patch("sopx.ingest.adapters.subprocess.run")
    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_get_info(self, mock_find, mock_run):
        raw_info = {
            "id": "ABC123",
            "title": "Test Video",
            "uploader": "Channel",
            "upload_date": "20250101",
            "duration": 300,
        }
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(raw_info), stderr=""
        )
        adapter = YtDlpAdapter()
        result = adapter.get_info("https://youtube.com/watch?v=abc")
        assert result["canonical_id"] == "ABC123"
        assert result["title"] == "Test Video"
        assert result["upload_date"] == "20250101"

    @patch("sopx.ingest.adapters.subprocess.run")
    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_get_info_error(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="ERROR: Video not found"
        )
        adapter = YtDlpAdapter()
        with pytest.raises(RuntimeError, match="yt-dlp falhou"):
            adapter.get_info("https://youtube.com/watch?v=bad")

    @patch("sopx.ingest.adapters.subprocess.Popen")
    @patch("sopx.ingest.adapters._find_binary", return_value="/usr/bin/yt-dlp")
    def test_download_audio(self, mock_find, mock_popen, tmp_path):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr.readline.side_effect = [
            "[download] 100% of ~1.00MiB\n", "",  # progress line + EOF
        ]
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        (tmp_path / "audio.mp3").write_bytes(b"fake audio")

        adapter = YtDlpAdapter()
        result = adapter.download_audio(
            "https://youtube.com/watch?v=abc", tmp_path
        )
        assert result.exists()
        assert result.suffix == ".mp3"


class TestFFmpegAdapter:
    @patch("sopx.ingest.adapters._find_binary")
    def test_init(self, mock_find):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        adapter = FFmpegAdapter()
        assert adapter.ffmpeg == "/usr/bin/ffmpeg"
        assert adapter.ffprobe == "/usr/bin/ffprobe"

    @patch("sopx.ingest.adapters.subprocess.run")
    @patch("sopx.ingest.adapters._find_binary")
    def test_extract_audio(self, mock_find, mock_run, tmp_path):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        video = tmp_path / "input.mp4"
        video.write_bytes(b"fake video")
        out_dir = tmp_path / "output"

        adapter = FFmpegAdapter()
        result = adapter.extract_audio(video, out_dir)
        assert result.name == "audio.mp3"

    @patch("sopx.ingest.adapters.subprocess.run")
    @patch("sopx.ingest.adapters._find_binary")
    def test_get_duration(self, mock_find, mock_run, tmp_path):
        mock_find.side_effect = lambda name: f"/usr/bin/{name}"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="342.5\n", stderr=""
        )
        adapter = FFmpegAdapter()
        duration = adapter.get_duration(tmp_path / "video.mp4")
        assert duration == 342.5


class TestWhisperAdapter:
    def test_format_timestamp_srt(self):
        from sopx.ingest.adapters import _format_timestamp_srt
        assert _format_timestamp_srt(0.0) == "00:00:00,000"
        assert _format_timestamp_srt(61.5) == "00:01:01,500"

    def test_segments_to_srt(self):
        from sopx.ingest.adapters import _segments_to_srt
        segs = [
            MagicMock(start=0.0, end=2.5, text=" Hello world"),
            MagicMock(start=3.0, end=5.0, text=" Second segment"),
        ]
        srt = _segments_to_srt(segs)
        assert "Hello world" in srt
        assert "Second segment" in srt

    def test_init_default_model(self):
        adapter = WhisperAdapter()
        assert adapter.model_size == "base"

    @patch("sopx.ingest.adapters.WhisperAdapter._load_model")
    def test_transcribe_to_srt(self, mock_load, tmp_path):
        seg1 = MagicMock(start=0.0, end=2.5, text=" Olá mundo")
        seg2 = MagicMock(start=3.0, end=5.0, text=" Segundo segmento")
        info = MagicMock(duration=5.0, language="pt")

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], info)

        adapter = WhisperAdapter()
        adapter._model = mock_model

        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"fake audio")
        out_dir = tmp_path / "output"

        srt_path = adapter.transcribe_to_srt(audio, out_dir)
        assert srt_path.exists()
        assert srt_path.name == "transcript.srt"
        content = srt_path.read_text()
        assert "Olá mundo" in content

    def test_basic_srt_to_text(self):
        srt = (
            "1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n"
            "2\n00:00:03,000 --> 00:00:05,000\nSecond line\n"
        )
        text = WhisperAdapter._basic_srt_to_text(srt)
        assert "Hello world" in text
        assert "Second line" in text
        assert "-->" not in text

    def test_load_model_import_error(self):
        adapter = WhisperAdapter()
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with pytest.raises(ImportError, match="faster-whisper não encontrado"):
                adapter._load_model()
