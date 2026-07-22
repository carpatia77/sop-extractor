from unittest.mock import MagicMock, patch

import ingest


def test_check_deps_reports_ok_when_all_present(capsys):
    with patch("sopx.ingest.pipeline.check_dependencies", return_value={"yt-dlp": True, "ffmpeg": True}):
        ok = ingest.check_deps()
    assert ok is True
    out = capsys.readouterr().out
    assert "yt-dlp" in out


def test_check_deps_reports_not_ok_when_missing(capsys):
    with patch("sopx.ingest.pipeline.check_dependencies", return_value={"yt-dlp": False, "ffmpeg": True}):
        ok = ingest.check_deps()
    assert ok is False


def test_main_check_flag_calls_check_deps():
    with patch("ingest.check_deps", return_value=True) as mock_check:
        code = ingest.main(["--check"])
    mock_check.assert_called_once()
    assert code == 0


def test_main_status_flag_calls_show_status():
    with patch("ingest.show_status") as mock_status:
        code = ingest.main(["--status"])
    mock_status.assert_called_once()
    assert code == 0


def test_main_without_source_prints_help_and_returns_1(capsys):
    code = ingest.main([])
    assert code == 1


def test_main_happy_path_prints_next_scan_command(tmp_path, capsys):
    from pathlib import Path
    fake_result = MagicMock(
        cached=False,
        output_dir=Path("output/abc"),
        srt=Path("output/abc/transcript.srt"),
        text=Path("output/abc/full_text.txt"),
    )
    with patch("sopx.config.ensure_config", return_value={"whisper": {"model_size": "base"}, "cache_enabled": True}), \
         patch("sopx.cache.CacheManager"), \
         patch("sopx.ingest.pipeline.IngestPipeline") as MockPipeline:
        MockPipeline.return_value.ingest.return_value = fake_result
        code = ingest.main(["some_video.mp4"])
    assert code == 0
    out = capsys.readouterr().out
    assert "sopx scan output/abc/transcript.srt --emit-prompt" in out


def test_main_file_not_found_returns_1(capsys):
    with patch("sopx.config.ensure_config", return_value={"whisper": {"model_size": "base"}, "cache_enabled": True}), \
         patch("sopx.cache.CacheManager"), \
         patch("sopx.ingest.pipeline.IngestPipeline") as MockPipeline:
        MockPipeline.return_value.ingest.side_effect = FileNotFoundError("nope")
        code = ingest.main(["missing.mp4"])
    assert code == 1
    assert "Erro" in capsys.readouterr().err


def test_main_rescue_frames_not_implemented_returns_1(capsys):
    with patch("sopx.config.ensure_config", return_value={"whisper": {"model_size": "base"}, "cache_enabled": True}), \
         patch("sopx.cache.CacheManager"), \
         patch("sopx.ingest.pipeline.IngestPipeline") as MockPipeline:
        MockPipeline.return_value.ingest.side_effect = NotImplementedError("use the script manually")
        code = ingest.main(["video.mp4", "--rescue-frames"])
    assert code == 1
    assert "não implementado" in capsys.readouterr().err
