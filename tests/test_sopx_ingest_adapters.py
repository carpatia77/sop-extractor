import json
from unittest.mock import MagicMock, patch

import pytest

from sopx.ingest.adapters import (
    FFmpegAdapter,
    WhisperAdapter,
    YtDlpAdapter,
    _format_timestamp_srt,
    _segments_to_srt,
    find_binary_safe,
)


def test_is_url_detects_http_and_https():
    assert YtDlpAdapter.is_url("https://youtube.com/watch?v=X")
    assert YtDlpAdapter.is_url("http://example.com/video")
    assert not YtDlpAdapter.is_url("/home/user/video.mp4")
    assert not YtDlpAdapter.is_url("video.mp4")


def test_find_binary_safe_returns_none_for_missing_binary():
    assert find_binary_safe("definitely-not-a-real-binary-xyz") is None


@patch("sopx.ingest.adapters.shutil.which", return_value="/usr/bin/yt-dlp")
@patch("sopx.ingest.adapters.subprocess.run")
def test_get_info_parses_canonical_fields(mock_run, mock_which):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "id": "ABC123", "title": "My Video", "uploader": "Someone",
            "upload_date": "20250101", "duration": 120,
        }),
        stderr="",
    )
    adapter = YtDlpAdapter()
    info = adapter.get_info("https://youtube.com/watch?v=ABC123")
    assert info["canonical_id"] == "ABC123"
    assert info["upload_date"] == "20250101"
    assert info["duration"] == 120


@patch("sopx.ingest.adapters.shutil.which", return_value="/usr/bin/yt-dlp")
@patch("sopx.ingest.adapters.subprocess.run")
def test_get_info_raises_on_nonzero_exit(mock_run, mock_which):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="video unavailable")
    adapter = YtDlpAdapter()
    with pytest.raises(RuntimeError, match="video unavailable"):
        adapter.get_info("https://youtube.com/watch?v=DEAD")


@patch("sopx.ingest.adapters.shutil.which", return_value="/usr/bin/yt-dlp")
@patch("sopx.ingest.adapters.subprocess.run")
def test_download_audio_returns_deterministic_mp3_path(mock_run, mock_which, tmp_path):
    def fake_download(*args, **kwargs):
        (tmp_path / "audio.mp3").write_bytes(b"fake-mp3")
        return MagicMock(returncode=0, stdout="", stderr="")
    mock_run.side_effect = fake_download

    adapter = YtDlpAdapter()
    result = adapter.download_audio("https://youtube.com/watch?v=X", tmp_path)
    assert result == tmp_path / "audio.mp3"
    assert result.exists()


@patch("sopx.ingest.adapters.shutil.which", return_value="/usr/bin/yt-dlp")
@patch("sopx.ingest.adapters.subprocess.run")
def test_download_audio_raises_if_mp3_never_materializes(mock_run, mock_which, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    adapter = YtDlpAdapter()
    with pytest.raises(FileNotFoundError):
        adapter.download_audio("https://youtube.com/watch?v=X", tmp_path)


@patch("sopx.ingest.adapters.shutil.which", return_value="/usr/bin/ffmpeg")
@patch("sopx.ingest.adapters.subprocess.run")
def test_extract_audio_writes_final_mp3_not_tmp(mock_run, mock_which, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video")
    out_dir = tmp_path / "out"

    def fake_ffmpeg(cmd, **kwargs):
        tmp_output = next(p for p in cmd if p.endswith(".tmp"))
        with open(tmp_output, "wb") as f:
            f.write(b"fake-audio")
        return MagicMock(returncode=0, stdout="", stderr="")
    mock_run.side_effect = fake_ffmpeg

    adapter = FFmpegAdapter()
    result = adapter.extract_audio(video, out_dir)
    assert result == out_dir / "audio.mp3"
    assert result.exists()
    assert not (out_dir / "audio.mp3.tmp").exists()


@patch("sopx.ingest.adapters.shutil.which", return_value="/usr/bin/ffmpeg")
@patch("sopx.ingest.adapters.subprocess.run")
def test_extract_audio_cleans_up_tmp_on_failure(mock_run, mock_which, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_ffmpeg(cmd, **kwargs):
        tmp_output = next(p for p in cmd if p.endswith(".tmp"))
        with open(tmp_output, "wb") as f:
            f.write(b"partial")
        return MagicMock(returncode=1, stdout="", stderr="boom")
    mock_run.side_effect = fake_ffmpeg

    adapter = FFmpegAdapter()
    with pytest.raises(RuntimeError):
        adapter.extract_audio(video, out_dir)
    assert not (out_dir / "audio.mp3.tmp").exists()
    assert not (out_dir / "audio.mp3").exists()


def test_format_timestamp_srt():
    assert _format_timestamp_srt(0) == "00:00:00,000"
    assert _format_timestamp_srt(90.5) == "00:01:30,500"
    assert _format_timestamp_srt(3661.25) == "01:01:01,250"


def test_segments_to_srt_formats_correctly():
    seg = MagicMock(start=0.0, end=2.0, text=" Hello world ")
    srt = _segments_to_srt([seg])
    assert "1\n00:00:00,000 --> 00:00:02,000\nHello world" in srt


def test_whisper_adapter_defaults_to_auto_detect_language():
    adapter = WhisperAdapter(model_size="base")
    assert adapter.language is None


def test_whisper_adapter_accepts_explicit_language():
    adapter = WhisperAdapter(model_size="base", language="pt")
    assert adapter.language == "pt"


def test_transcribe_to_srt_writes_final_file_not_tmp(tmp_path):
    adapter = WhisperAdapter(model_size="base")
    seg = MagicMock(start=0.0, end=1.0, text="oi")
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([seg], MagicMock(duration=1.0, language="pt"))
    adapter._model = fake_model

    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake")
    out_dir = tmp_path / "srt_out"

    result = adapter.transcribe_to_srt(audio_path, out_dir)
    assert result == out_dir / "transcript.srt"
    assert result.exists()
    assert not (out_dir / "transcript.srt.tmp").exists()
    fake_model.transcribe.assert_called_once()
    _, kwargs = fake_model.transcribe.call_args
    assert kwargs["language"] is None


def test_basic_srt_to_text_strips_structure():
    srt = "1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n2\n00:00:02,000 --> 00:00:04,000\nBye\n"
    text = WhisperAdapter._basic_srt_to_text(srt)
    assert text == "Hello world\nBye"
