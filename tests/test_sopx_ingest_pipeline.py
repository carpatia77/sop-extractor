import json
from unittest.mock import MagicMock

import pytest

from sopx.cache import CacheManager
from sopx.ingest.pipeline import IngestPipeline, check_dependencies


def _make_pipeline(tmp_path, cache_enabled=True):
    config = {
        "language": "pt-BR",
        "cache_enabled": cache_enabled,
        "output_dir": str(tmp_path / "output"),
        "whisper": {"model_size": "base"},
        "rescue_frames": False,
    }
    cache = CacheManager(tmp_path / "cache")
    pipeline = IngestPipeline(config=config, cache=cache)
    return pipeline


def _stub_whisper(pipeline, text="hello world"):
    fake_whisper = MagicMock()

    def fake_transcribe(audio_path, out_dir):
        from pathlib import Path
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        srt_path = out_dir / "transcript.srt"
        srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n" + text + "\n", encoding="utf-8"
        )
        return srt_path, text
    fake_whisper.transcribe_to_text.side_effect = fake_transcribe
    pipeline._whisper = fake_whisper
    return fake_whisper


def test_ingest_raises_for_missing_local_file(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    with pytest.raises(FileNotFoundError):
        pipeline.ingest(str(tmp_path / "does_not_exist.mp4"))


def test_ingest_rescue_frames_raises_not_implemented(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    with pytest.raises(NotImplementedError):
        pipeline.ingest(str(video), rescue_frames=True)


def test_ingest_local_file_produces_expected_outputs(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video-bytes")

    fake_ffmpeg = MagicMock()

    def fake_extract_audio(source, out_dir):
        from pathlib import Path
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "audio.mp3"
        audio_path.write_bytes(b"fake-audio")
        return audio_path
    fake_ffmpeg.extract_audio.side_effect = fake_extract_audio
    fake_ffmpeg.get_duration.return_value = 42.0
    pipeline._ffmpeg = fake_ffmpeg

    _stub_whisper(pipeline, text="conteudo transcrito")

    result = pipeline.ingest(str(video))

    assert result.cached is False
    assert result.srt.exists()
    assert result.text.read_text(encoding="utf-8") == "conteudo transcrito"
    metadata = json.loads(result.metadata.read_text(encoding="utf-8"))
    assert metadata["duration_seconds"] == 42.0
    assert metadata["word_count"] == 2
    assert metadata["title"] == "video"

    # Stage cache must actually be populated for the local-file branch too.
    key = CacheManager.key_for_file(video)
    assert pipeline.cache.is_stage_done(key, "audio") is True
    assert pipeline.cache.is_stage_done(key, "srt") is True


def test_ingest_second_run_is_a_full_cache_hit(tmp_path):
    pipeline = _make_pipeline(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video-bytes")

    fake_ffmpeg = MagicMock()

    def fake_extract_audio(source, out_dir):
        from pathlib import Path
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "audio.mp3"
        audio_path.write_bytes(b"fake-audio")
        return audio_path
    fake_ffmpeg.extract_audio.side_effect = fake_extract_audio
    fake_ffmpeg.get_duration.return_value = 1.0
    pipeline._ffmpeg = fake_ffmpeg
    _stub_whisper(pipeline)

    first = pipeline.ingest(str(video))
    assert first.cached is False

    second = pipeline.ingest(str(video))
    assert second.cached is True
    assert second.output_dir == first.output_dir
    # ffmpeg/whisper must not be invoked again on the cache-hit path.
    assert fake_ffmpeg.extract_audio.call_count == 1


def test_ingest_audio_stage_cache_survives_a_whisper_crash(tmp_path):
    """Regression: the stage-cache existed precisely so a whisper crash
    doesn't force re-downloading/re-extracting audio. Verify the audio
    stage is reused on retry after a first attempt fails at the SRT stage."""
    pipeline = _make_pipeline(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video-bytes")

    fake_ffmpeg = MagicMock()

    def fake_extract_audio(source, out_dir):
        from pathlib import Path
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "audio.mp3"
        audio_path.write_bytes(b"fake-audio")
        return audio_path
    fake_ffmpeg.extract_audio.side_effect = fake_extract_audio
    fake_ffmpeg.get_duration.return_value = 1.0
    pipeline._ffmpeg = fake_ffmpeg

    failing_whisper = MagicMock()
    failing_whisper.transcribe_to_text.side_effect = RuntimeError("whisper crashed")
    pipeline._whisper = failing_whisper

    with pytest.raises(RuntimeError, match="whisper crashed"):
        pipeline.ingest(str(video))

    assert fake_ffmpeg.extract_audio.call_count == 1
    key = CacheManager.key_for_file(video)
    assert pipeline.cache.is_stage_done(key, "audio") is True
    assert pipeline.cache.is_stage_done(key, "srt") is False

    # Retry: audio stage must be reused, not re-extracted.
    _stub_whisper(pipeline, text="segunda tentativa")
    result = pipeline.ingest(str(video))
    assert result.cached is False
    assert fake_ffmpeg.extract_audio.call_count == 1  # unchanged — reused from stage cache


def test_ingest_with_cache_disabled_reprocesses_every_time(tmp_path):
    pipeline = _make_pipeline(tmp_path, cache_enabled=False)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-video-bytes")

    fake_ffmpeg = MagicMock()

    def fake_extract_audio(source, out_dir):
        from pathlib import Path
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "audio.mp3"
        audio_path.write_bytes(b"fake-audio")
        return audio_path
    fake_ffmpeg.extract_audio.side_effect = fake_extract_audio
    fake_ffmpeg.get_duration.return_value = 1.0
    pipeline._ffmpeg = fake_ffmpeg
    _stub_whisper(pipeline)

    pipeline.ingest(str(video))
    pipeline.ingest(str(video))
    assert fake_ffmpeg.extract_audio.call_count == 2


def test_check_dependencies_reports_dict_of_bools():
    deps = check_dependencies()
    assert set(deps.keys()) == {"yt-dlp", "ffmpeg", "ffprobe", "faster-whisper"}
    assert all(isinstance(v, bool) for v in deps.values())
