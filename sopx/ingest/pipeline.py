"""Ingest Pipeline — orchestrates URL/file → SRT → text → output.

Cache is checked per stage: (1) input→audio and (2) audio→SRT are
separate artifacts, so a whisper crash doesn't re-download audio.

Progress tracking:
  - Pipeline stage: printed to stderr (Metadata → Download → Transcrever → Salvar)
  - Download progress: tqdm bar in YtDlpAdapter
  - Transcription progress: tqdm bar in WhisperAdapter
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from sopx.cache import CacheManager
from sopx.config import ensure_config, get
from sopx.ingest.adapters import FFmpegAdapter, WhisperAdapter, YtDlpAdapter

# Pipeline stage labels
_STAGES = ["Metadata", "Download", "Transcrever", "Salvar"]

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of a successful ingestion."""
    output_dir: Path
    srt: Path
    text: Path
    metadata: Path
    cached: bool


class IngestPipeline:
    """Main ingestion pipeline: source → transcript → text output."""

    def __init__(self, config: dict | None = None, cache: CacheManager | None = None):
        self.config = config or ensure_config()
        self.cache = cache or CacheManager()
        self._ytdlp: YtDlpAdapter | None = None
        self._ffmpeg: FFmpegAdapter | None = None
        self._whisper: WhisperAdapter | None = None

    @property
    def ytdlp(self) -> YtDlpAdapter:
        if self._ytdlp is None:
            self._ytdlp = YtDlpAdapter()
        return self._ytdlp

    @property
    def ffmpeg(self) -> FFmpegAdapter:
        if self._ffmpeg is None:
            self._ffmpeg = FFmpegAdapter()
        return self._ffmpeg

    @property
    def whisper(self) -> WhisperAdapter:
        if self._whisper is None:
            model = get(self.config, "whisper.model_size", "base")
            self._whisper = WhisperAdapter(model_size=model)
        return self._whisper

    def _print_stage(self, stage: str):
        """Print pipeline stage indicator to stderr."""
        idx = _STAGES.index(stage) + 1 if stage in _STAGES else 0
        total = len(_STAGES)
        print(f"\n  [{idx}/{total}] {stage} ...", file=sys.stderr)

    def ingest(
        self,
        source: str,
        output_base: str | Path | None = None,
        rescue_frames: bool = False,
    ) -> IngestResult:
        """Run the full ingestion pipeline.

        Args:
            source: URL (http/https) or local file path.
            output_base: Base directory for outputs (default from config).
            rescue_frames: If True, extract key frames at deictic timestamps.

        Returns:
            IngestResult with paths to generated files.
        """
        if output_base is None:
            output_base = get(self.config, "output_dir", "output/")
        output_base = Path(output_base)

        is_url = YtDlpAdapter.is_url(source)

        # --- Stage: Metadata ---
        self._print_stage("Metadata")
        if is_url:
            info = self.ytdlp.get_info(source)
            key = CacheManager.key_for_url(info["canonical_id"])
        else:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {source}")
            key = CacheManager.key_for_file(path)
            info = {"canonical_id": "", "title": path.stem}

        # Check full cache
        if get(self.config, "cache_enabled", True) and self.cache.is_done(key):
            output_dir = Path(self.cache.get_output_dir(key))
            log.info("Cache hit para %s", key)
            print(f"\n  Cache hit — reutilizando output anterior", file=sys.stderr)
            return IngestResult(
                output_dir=output_dir,
                srt=output_dir / "transcript.srt",
                text=output_dir / "full_text.txt",
                metadata=output_dir / "metadata.json",
                cached=True,
            )

        # --- Create output directory ---
        cache_enabled = get(self.config, "cache_enabled", True)
        if not cache_enabled:
            ts = time.strftime("%Y%m%d_%H%M%S")
            output_dir = output_base / f"{key}_{ts}"
        else:
            output_dir = output_base / key
        output_dir.mkdir(parents=True, exist_ok=True)

        # --- Stage: Download ---
        self._print_stage("Download")
        audio_path = None
        if get(self.cache, "_index", {}).get(f"{key}:audio"):
            audio_dir = self.cache.stage_path(key, "audio")
            audio_files = list(audio_dir.glob("audio.*"))
            if audio_files:
                audio_path = audio_files[0]
                print(f"  Audio cache hit", file=sys.stderr)

        if audio_path is None:
            if is_url:
                audio_dir = self.cache.stage_path(key, "audio")
                audio_path = self.ytdlp.download_audio(source, audio_dir)
            else:
                audio_path = self.ffmpeg.extract_audio(source, output_dir)

        # --- Stage: Transcrever ---
        self._print_stage("Transcrever")
        srt_path = None
        plain_text = None
        if self.cache.is_stage_done(key, "srt"):
            srt_dir = self.cache.stage_path(key, "srt")
            srt_file = srt_dir / "transcript.srt"
            if srt_file.exists():
                srt_path = srt_file
                plain_text = srt_path.read_text(encoding="utf-8")
                print(f"  SRT cache hit", file=sys.stderr)

        if srt_path is None:
            srt_dir = self.cache.stage_path(key, "srt")
            srt_path, plain_text = self.whisper.transcribe_to_text(audio_path, srt_dir)

        # --- Stage: Salvar ---
        self._print_stage("Salvar")
        final_srt = output_dir / "transcript.srt"
        final_srt.write_text(srt_path.read_text(encoding="utf-8"), encoding="utf-8")

        text_path = output_dir / "full_text.txt"
        text_path.write_text(plain_text, encoding="utf-8")

        duration = 0
        if is_url:
            duration = info.get("duration", 0)
        else:
            try:
                duration = self.ffmpeg.get_duration(source)
            except Exception:
                pass

        word_count = len(plain_text.split())
        upload_date = info.get("upload_date", "")
        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        metadata = {
            "source": source,
            "canonical_id": info.get("canonical_id", ""),
            "title": info.get("title", ""),
            "uploader": info.get("uploader", ""),
            "upload_date": upload_date,
            "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_seconds": duration,
            "whisper_model": get(self.config, "whisper.model_size", "base"),
            "language": get(self.config, "language", "pt-BR"),
            "word_count": word_count,
        }
        meta_path = output_dir / "metadata.json"
        meta_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self.cache.mark_done(
            key, str(output_dir),
            canonical_id=info.get("canonical_id", ""),
            word_count=word_count,
            title=info.get("title", ""),
        )

        log.info("Ingestão concluída: %d palavras em %s", word_count, output_dir)

        return IngestResult(
            output_dir=output_dir,
            srt=final_srt,
            text=text_path,
            metadata=meta_path,
            cached=False,
        )


def check_dependencies() -> dict[str, bool]:
    """Check which ingestion dependencies are available."""
    import shutil
    deps = {}
    for name in ["yt-dlp", "ffmpeg", "ffprobe"]:
        deps[name] = shutil.which(name) is not None
    try:
        import faster_whisper  # noqa: F401
        deps["faster-whisper"] = True
    except ImportError:
        deps["faster-whisper"] = False
    return deps
