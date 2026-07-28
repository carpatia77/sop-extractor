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
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from sopx.cache import CacheManager
from sopx.config import ensure_config, get
from sopx.ingest.adapters import FFmpegAdapter, WhisperAdapter, YtDlpAdapter

# Pipeline stage labels
_STAGES = ["Metadata", "Download", "Transcrever", "Salvar"]


def _format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    if seconds <= 0:
        return "N/A"
    seconds = int(seconds)
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _estimate_transcription_time(duration: float, model: str) -> float:
    """Estimate transcription time in seconds based on video duration and model.

    Uses hardware-aware speed ratios from sopx.ingest.hardware module.
    """
    from sopx.ingest.hardware import detect_hardware, estimate_transcription_time as _est
    profile = detect_hardware()
    return _est(duration, model, profile)

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of a successful ingestion."""
    output_dir: Path
    srt: Path
    text: Path
    metadata: Path
    cached: bool
    total_elapsed: float = 0.0
    word_count: int = 0
    title: str = ""
    duration: float = 0.0


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
            # Eagerly load hardware profile for summary
            self._whisper._get_profile()
        return self._whisper

    def _print_stage(self, stage: str):
        """Print pipeline stage indicator to stderr."""
        idx = _STAGES.index(stage) + 1 if stage in _STAGES else 0
        total = len(_STAGES)
        print(f"\n  [{idx}/{total}] {stage} ...", file=sys.stderr)

    def _print_summary(self, info: dict, source: str):
        """Print video summary with estimated processing time and hardware info."""
        from sopx.ingest.hardware import detect_hardware, get_optimal_settings

        title = info.get("title", "N/A")
        uploader = info.get("uploader", "")
        duration = info.get("duration", 0)
        model = get(self.config, "whisper.model_size", "base")

        duration_str = _format_duration(duration)
        est_time = _estimate_transcription_time(duration, model)
        est_str = _format_duration(est_time)

        # Hardware info
        profile = detect_hardware()
        settings = get_optimal_settings(profile, duration)
        tier_names = {"low": "Baixo", "medium": "Médio", "high": "Alto"}
        gpu_str = " + GPU" if profile.has_gpu else ""

        # Segment info for long videos
        segment_info = ""
        if settings["split_audio"]:
            num_segments = int(duration / settings["max_segment_sec"]) + 1
            segment_info = f" ({num_segments} segments)"

        # Truncate long titles
        if len(title) > 72:
            title = title[:69] + "..."

        print("\n  ┌─ Resumo ─────────────────────────────────", file=sys.stderr)
        print(f"  │ Título:     {title}", file=sys.stderr)
        if uploader:
            print(f"  │ Canal:      {uploader}", file=sys.stderr)
        print(f"  │ Duração:    {duration_str}", file=sys.stderr)
        print(f"  │ Modelo:     whisper {model}", file=sys.stderr)
        print(f"  │ Hardware:   {tier_names.get(profile.tier, '?')} ({profile.cpu_physical} cores, {profile.ram_gb:.0f}GB{gpu_str})", file=sys.stderr)
        print(f"  │ Batch:      {settings['batch_size']}", file=sys.stderr)
        print(f"  │ ETA:        ~{est_str} de transcrição{segment_info}", file=sys.stderr)
        print("  └──────────────────────────────────────────\n", file=sys.stderr)

    def _print_completion(self, info: dict, result: IngestResult):
        """Print completion summary with all info and total time."""
        title = info.get("title", "N/A")
        if len(title) > 60:
            title = title[:57] + "..."
        elapsed = _format_duration(result.total_elapsed)
        video_dur = _format_duration(result.duration)

        print("\n  ┌─ Ingestão Concluída ────────────────────", file=sys.stderr)
        print(f"  │ Título:      {title}", file=sys.stderr)
        print(f"  │ Duração:     {video_dur} de vídeo", file=sys.stderr)
        print(f"  │ Palavras:    {result.word_count}", file=sys.stderr)
        print(f"  │ Tempo total: {elapsed}", file=sys.stderr)
        print(f"  │ Output:      {result.output_dir}", file=sys.stderr)
        print("  └──────────────────────────────────────────", file=sys.stderr)

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
        t_start = time.time()

        # --- Stage: Metadata ---
        self._print_stage("Metadata")
        if is_url:
            info = self.ytdlp.get_info(source)
            key = CacheManager.key_for_url(info["canonical_id"])
            self._print_summary(info, source)
        else:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {source}")
            key = CacheManager.key_for_file(path)
            info = {"canonical_id": "", "title": path.stem}
            # For local files, get duration for summary
            try:
                info["duration"] = self.ffmpeg.get_duration(source)
            except Exception:
                info["duration"] = 0
            info["uploader"] = ""
            self._print_summary(info, source)

        # Check full cache
        if get(self.config, "cache_enabled", True) and self.cache.is_done(key):
            output_dir = Path(self.cache.get_output_dir(key))
            log.info("Cache hit para %s", key)
            elapsed = time.time() - t_start
            result = IngestResult(
                output_dir=output_dir,
                srt=output_dir / "transcript.srt",
                text=output_dir / "full_text.txt",
                metadata=output_dir / "metadata.json",
                cached=True,
                total_elapsed=elapsed,
                title=info.get("title", ""),
                duration=info.get("duration", 0),
            )
            print("\n  Cache hit — reutilizando output anterior", file=sys.stderr)
            return result

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
        cache_enabled = get(self.config, "cache_enabled", True)
        if cache_enabled and self.cache.is_stage_done(key, "audio"):
            audio_dir = self.cache.stage_path(key, "audio")
            audio_files = list(audio_dir.glob("audio.*"))
            if audio_files:
                audio_path = audio_files[0]
                print("  Audio cache hit", file=sys.stderr)

        if audio_path is None:
            audio_dir = self.cache.stage_path(key, "audio")
            if is_url:
                audio_path = self.ytdlp.download_audio(source, audio_dir)
            else:
                audio_path = self.ffmpeg.extract_audio(source, audio_dir)
            if cache_enabled:
                self.cache.mark_stage_done(key, "audio")

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
                print("  SRT cache hit", file=sys.stderr)

        if srt_path is None:
            srt_dir = self.cache.stage_path(key, "srt")
            srt_path, plain_text = self.whisper.transcribe_to_text(audio_path, srt_dir)
            if cache_enabled:
                self.cache.mark_stage_done(key, "srt")

        # --- Stage: Salvar ---
        self._print_stage("Salvar")
        final_srt = output_dir / "transcript.srt"
        final_srt.write_text(srt_path.read_text(encoding="utf-8"), encoding="utf-8")

        text_path = output_dir / "full_text.txt"
        text_path.write_text(plain_text, encoding="utf-8")

        # --- Stage: Frames (optional) ---
        # Frame extraction only works with LOCAL video files (not audio from URLs)
        frames_dir = None
        if rescue_frames and not is_url:
            self._print_stage("Frames")
            try:
                from scripts.extract_frames_at_timestamps import (
                    find_gap_timestamps, dedupe_timestamps, extract_frames,
                )
                # Use SRT content (with timestamps) not plain_text (without timestamps)
                srt_content = srt_path.read_text(encoding="utf-8") if srt_path else ""
                hits = find_gap_timestamps(srt_content)
                hits = dedupe_timestamps(hits)
                if hits:
                    frames_dir = output_dir / "frames"
                    frames_dir.mkdir(exist_ok=True)
                    manifest = extract_frames(str(source), hits, str(frames_dir))
                    log.info("Extraídos %d frames em %s", len(manifest), frames_dir)
                else:
                    print("  Nenhum timestamp deictic encontrado", file=sys.stderr)
            except ImportError:
                log.warning("scripts/extract_frames_at_timestamps.py não encontrado")
            except Exception as e:
                log.warning("Falha na extração de frames: %s", e)

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

        elapsed = time.time() - t_start
        log.info("Ingestão concluída: %d palavras em %s (%.0fs)", word_count, output_dir, elapsed)

        result = IngestResult(
            output_dir=output_dir,
            srt=final_srt,
            text=text_path,
            metadata=meta_path,
            cached=False,
            total_elapsed=elapsed,
            word_count=word_count,
            title=info.get("title", ""),
            duration=info.get("duration", 0),
        )
        self._print_completion(info, result)
        return result

    def ingest_playlist(
        self,
        playlist_url: str,
        output_base: str | Path | None = None,
        max_videos: int | None = None,
        workers: int = 1,
    ) -> list[IngestResult]:
        """Ingest all videos from a YouTube playlist or channel.

        Args:
            playlist_url: URL of the playlist or channel.
            output_base: Base directory for outputs.
            max_videos: Maximum number of videos to process (None = all).
            workers: Number of parallel ingest workers (default 1).

        Returns:
            List of IngestResult for each successfully ingested video.
        """
        if output_base is None:
            output_base = get(self.config, "output_dir", "output/")
        output_base = Path(output_base)

        # Get playlist info
        print("\n  Buscando vídeos do playlist...", file=sys.stderr)
        cmd = [
            self.ytdlp.binary,
            "--flat-playlist",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            playlist_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp falhou ao listar playlist: {result.stderr.strip()}")

        # Parse video IDs
        video_ids = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            info = json.loads(line)
            video_ids.append(info.get("id", ""))

        if max_videos:
            video_ids = video_ids[:max_videos]

        total = len(video_ids)
        print(f"  Encontrados {total} vídeos para processar", file=sys.stderr)
        if workers > 1:
            print(f"  Workers paralelos: {workers}", file=sys.stderr)
        print("", file=sys.stderr)

        # Check cache — skip already-processed videos (resume support)
        cached = 0
        to_process = []
        cache = getattr(self, "cache", None)
        for video_id in video_ids:
            url = f"https://www.youtube.com/watch?v={video_id}"
            if cache:
                key = CacheManager.key_for_url(video_id)
                if cache.is_done(key):
                    cached += 1
                    continue
            to_process.append((video_id, url))

        if cached:
            print(f"  Cache: {cached}/{total} já processados (serão pulados)", file=sys.stderr)
        if not to_process:
            print(f"  Todos os {total} vídeos já processados.", file=sys.stderr)
            return []

        print(f"  A processar: {len(to_process)} vídeos\n", file=sys.stderr)

        # Process videos
        t_start = time.time()
        results = []
        completed = 0
        failed = 0

        def _ingest_one(item):
            idx, (video_id, url) = item
            return idx, video_id, self.ingest(url, output_base=output_base)

        if workers <= 1:
            # Sequential (original behavior)
            for i, (video_id, url) in enumerate(to_process, 1):
                _print_batch_progress(i, len(to_process), video_id, t_start)
                try:
                    result = self.ingest(url, output_base=output_base)
                    results.append(result)
                    completed += 1
                except Exception as e:
                    log.warning("Falha ao processar %s: %s", video_id, e)
                    print(f"  ⚠ Erro: {e}", file=sys.stderr)
                    failed += 1
        else:
            # Parallel with ThreadPoolExecutor
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_ingest_one, (i, item)): item
                    for i, item in enumerate(to_process, 1)
                }
                for future in as_completed(futures):
                    try:
                        idx, video_id, result = future.result()
                        results.append(result)
                        completed += 1
                        _print_batch_progress(completed + failed, len(to_process), video_id, t_start)
                    except Exception as e:
                        failed += 1
                        item = futures[future]
                        log.warning("Falha ao processar %s: %s", item[0], e)
                        print(f"  ⚠ Erro: {e}", file=sys.stderr)
                        _print_batch_progress(completed + failed, len(to_process), item[0], t_start)

        # Summary
        elapsed = time.time() - t_start
        _print_batch_summary(total, cached, completed, failed, elapsed)

        return results


def _print_batch_progress(current: int, total: int, video_id: str, t_start: float) -> None:
    """Print batch progress with ETA."""
    elapsed = time.time() - t_start
    avg = elapsed / max(current, 1)
    remaining = avg * (total - current)
    h, m, s = int(remaining // 3600), int((remaining % 3600) // 60), int(remaining % 60)
    eta = f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"
    print(
        f"\r  [{current}/{total}] {video_id}  |  ETA: {eta}  ",
        end="", file=sys.stderr, flush=True,
    )
    if current == total:
        print(file=sys.stderr)  # newline after final


def _print_batch_summary(total: int, cached: int, completed: int, failed: int, elapsed: float) -> None:
    """Print batch completion summary."""
    h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
    duration = f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"
    print("\n  ═══════════════════════════════════════════", file=sys.stderr)
    print("  Resumo do batch:", file=sys.stderr)
    print(f"  ├─ Total:     {total} vídeos", file=sys.stderr)
    if cached:
        print(f"  ├─ Cache:     {cached} (já processados)", file=sys.stderr)
    print(f"  ├─ Sucesso:   {completed}", file=sys.stderr)
    print(f"  ├─ Falhas:    {failed}", file=sys.stderr)
    print(f"  └─ Tempo:     {duration}", file=sys.stderr)
    print("  ═══════════════════════════════════════════\n", file=sys.stderr)


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
