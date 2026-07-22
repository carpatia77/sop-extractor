"""Ingest Pipeline — orchestrates URL/file → SRT → text → output.

Cache is checked per stage: (1) input→audio and (2) audio→SRT are
separate artifacts, so a whisper crash doesn't re-download audio.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sopx.cache import CacheManager
from sopx.config import ensure_config, get
from sopx.ingest.adapters import FFmpegAdapter, WhisperAdapter, YtDlpAdapter

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
            language = get(self.config, "language", None)
            self._whisper = WhisperAdapter(model_size=model, language=language)
        return self._whisper

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
            rescue_frames: Local-file sources only — visual-reference frame
                rescue needs the source video, which URL ingestion never
                keeps (only its audio is downloaded). Not yet wired to
                scripts/extract_frames_at_timestamps.py; raises
                NotImplementedError rather than silently doing nothing, so
                the flag never lies about what ran.

        Returns:
            IngestResult with paths to generated files.
        """
        if rescue_frames:
            raise NotImplementedError(
                "--rescue-frames ainda não está integrado ao pipeline de ingestão. "
                "Rode manualmente após a ingestão: "
                "python scripts/extract_frames_at_timestamps.py <transcript.srt> "
                "--video <video_local> --output-dir <output>/frames"
            )

        if output_base is None:
            output_base = get(self.config, "output_dir", "output/")
        output_base = Path(output_base)

        cache_enabled = get(self.config, "cache_enabled", True)
        is_url = YtDlpAdapter.is_url(source)

        # --- Resolve key + cache ---
        if is_url:
            # Get canonical video-ID first
            info = self.ytdlp.get_info(source)
            key = CacheManager.key_for_url(info["canonical_id"])
        else:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {source}")
            key = CacheManager.key_for_file(path)
            info = {"canonical_id": "", "title": path.stem, "upload_date": "", "duration": 0}

        # Check full cache (also revalidates output_dir still exists on disk —
        # an index entry survives a deleted output/ folder otherwise)
        if cache_enabled and self.cache.is_done(key):
            output_dir = Path(self.cache.get_output_dir(key))
            log.info("Cache hit para %s", key)
            return IngestResult(
                output_dir=output_dir,
                srt=output_dir / "transcript.srt",
                text=output_dir / "full_text.txt",
                metadata=output_dir / "metadata.json",
                cached=True,
            )

        # --- Create output directory ---
        output_dir = output_base / key
        output_dir.mkdir(parents=True, exist_ok=True)

        # --- Stage 1: audio ---
        audio_path = None
        if cache_enabled and self.cache.is_stage_done(key, "audio"):
            audio_path = self.cache.stage_path(key, "audio") / "audio.mp3"
            if not audio_path.exists():
                audio_path = None  # sentinel present but file missing — re-run the stage

        if audio_path is None:
            audio_dir = self.cache.stage_path(key, "audio")
            if is_url:
                audio_path = self.ytdlp.download_audio(source, audio_dir)
            else:
                # Local video's audio also lands in the stage dir (not
                # output_dir directly) — otherwise it would never populate
                # the stage cache and every run would re-extract it.
                audio_path = self.ffmpeg.extract_audio(source, audio_dir)
            if cache_enabled:
                self.cache.mark_stage_done(key, "audio")

        # --- Stage 2: SRT ---
        srt_path = None
        plain_text = None
        if cache_enabled and self.cache.is_stage_done(key, "srt"):
            srt_dir = self.cache.stage_path(key, "srt")
            srt_file = srt_dir / "transcript.srt"
            if srt_file.exists():
                srt_path = srt_file
                plain_text = _plain_text_from_srt(srt_path)

        if srt_path is None:
            srt_dir = self.cache.stage_path(key, "srt")
            srt_path, plain_text = self.whisper.transcribe_to_text(audio_path, srt_dir)
            if cache_enabled:
                self.cache.mark_stage_done(key, "srt")

        # --- Write outputs ---
        # Copy SRT to output dir
        final_srt = output_dir / "transcript.srt"
        final_srt.write_text(srt_path.read_text(encoding="utf-8"), encoding="utf-8")

        # Write full_text.txt
        text_path = output_dir / "full_text.txt"
        text_path.write_text(plain_text, encoding="utf-8")

        # Write metadata.json (schematized provenance)
        if is_url:
            duration = info.get("duration", 0)
        else:
            try:
                duration = self.ffmpeg.get_duration(source)
            except Exception:
                duration = 0

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

        # --- Mark done ---
        if cache_enabled:
            self.cache.mark_done(key, str(output_dir), canonical_id=info.get("canonical_id", ""))

        log.info("Ingestão concluída: %d palavras em %s", word_count, output_dir)

        return IngestResult(
            output_dir=output_dir,
            srt=final_srt,
            text=text_path,
            metadata=meta_path,
            cached=False,
        )


def _plain_text_from_srt(srt_path: Path) -> str:
    """Derive plain text from a cached SRT, preferring the shared
    book_to_skill stripper and falling back to a minimal local one when
    the package isn't installed (scripts/ stays usable standalone)."""
    raw = srt_path.read_text(encoding="utf-8")
    try:
        from book_to_skill.parsers.subtitle import strip_subtitle_markup
        return strip_subtitle_markup(raw)
    except ImportError:
        from sopx.ingest.adapters import WhisperAdapter
        return WhisperAdapter._basic_srt_to_text(raw)


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
