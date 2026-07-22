"""Media adapters — wrappers for yt-dlp, ffmpeg, and faster-whisper.

Each adapter encapsulates one external tool, handles binary detection,
and raises clear Portuguese error messages on failure.

Scope note: ffmpeg is ONLY for local video files. For URLs, yt-dlp
handles audio extraction internally via -x flag.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# yt-dlp download timeout — generous because long courses over a slow
# connection routinely exceed a "safe-looking" couple of minutes.
DOWNLOAD_TIMEOUT_SECONDS = 1800


# ---------------------------------------------------------------------------
# Binary detection helpers
# ---------------------------------------------------------------------------

def _find_binary(name: str) -> str:
    """Find a binary on PATH. Raises FileNotFoundError with install hint."""
    path = shutil.which(name)
    if path:
        return path
    hints = {
        "yt-dlp": "pip install yt-dlp  ou  brew install yt-dlp",
        "ffmpeg": "apt install ffmpeg  ou  brew install ffmpeg",
        "ffprobe": "apt install ffmpeg  ou  brew install ffmpeg",
    }
    hint = hints.get(name, f"instale {name}")
    raise FileNotFoundError(
        f"'{name}' não encontrado no PATH. Instale com: {hint}"
    )


def find_binary_safe(name: str) -> str | None:
    """Find a binary on PATH without raising. Returns None if missing."""
    return shutil.which(name)


# ---------------------------------------------------------------------------
# yt-dlp Adapter
# ---------------------------------------------------------------------------

class YtDlpAdapter:
    """Download videos and extract metadata via yt-dlp."""

    def __init__(self):
        self.binary = self._find_binary()

    def _find_binary(self) -> str:
        return _find_binary("yt-dlp")

    @staticmethod
    def is_url(source: str) -> bool:
        """Return True if source looks like a URL."""
        return source.startswith("http://") or source.startswith("https://")

    def get_info(self, url: str) -> dict:
        """Extract video metadata including canonical video-ID.

        Returns dict with keys: canonical_id, title, uploader, upload_date
        (YYYYMMDD, as yt-dlp reports it — normalized to YYYY-MM-DD by the
        pipeline before it's written to metadata.json), duration.
        """
        cmd = [
            self.binary,
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"yt-dlp falhou ao obter metadata: {result.stderr.strip()}"
            )
        info = json.loads(result.stdout)
        return {
            "canonical_id": info.get("id", ""),
            "title": info.get("title", ""),
            "uploader": info.get("uploader", ""),
            "upload_date": info.get("upload_date", ""),  # YYYYMMDD or ""
            "duration": info.get("duration", 0),
        }

    def download_audio(self, url: str, output_dir: str | Path) -> Path:
        """Download audio-only from a URL, saved as output_dir/audio.mp3.

        Uses yt-dlp -x --audio-format mp3, which internally calls ffmpeg
        for extraction. The output template constrains the extension so
        the result is deterministic — no globbing for "whatever yt-dlp
        happened to name it", which could otherwise pick up a stray
        leftover (.part, a residual pre-conversion container) instead of
        the finished .mp3.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        final_path = output_dir / "audio.mp3"
        output_template = str(output_dir / "audio.%(ext)s")
        cmd = [
            self.binary,
            "-x",                          # extract audio
            "--audio-format", "mp3",
            "--audio-quality", "2",
            "-o", output_template,
            "--no-playlist",
            url,
        ]
        log.info("Baixando áudio de %s ...", url)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"yt-dlp falhou ao baixar áudio: {result.stderr.strip()}"
            )

        if not final_path.exists():
            raise FileNotFoundError(
                f"yt-dlp não gerou '{final_path.name}' em {output_dir}. "
                "Verifique a URL e se --audio-format mp3 foi respeitado."
            )
        return final_path


# ---------------------------------------------------------------------------
# FFmpeg Adapter — ONLY for local video files
# ---------------------------------------------------------------------------

class FFmpegAdapter:
    """Extract audio from LOCAL video files via ffmpeg/ffprobe.

    For URLs, use YtDlpAdapter which handles audio extraction internally.
    """

    def __init__(self):
        self.ffmpeg = _find_binary("ffmpeg")
        self.ffprobe = _find_binary("ffprobe")

    def extract_audio(
        self, video_path: str | Path, output_dir: str | Path
    ) -> Path:
        """Extract audio track from a LOCAL video file as MP3.

        Writes to a temp file first and renames into place atomically —
        so a crash mid-extraction never leaves a half-written audio.mp3
        that a later stage-cache check could mistake for a finished one.
        """
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        final_path = output_dir / "audio.mp3"
        tmp_path = output_dir / "audio.mp3.tmp"
        cmd = [
            self.ffmpeg,
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            "-y",
            str(tmp_path),
        ]
        log.info("Extraindo áudio de %s ...", video_path.name)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"ffmpeg falhou ao extrair áudio: {result.stderr[-500:]}"
            )
        os.replace(tmp_path, final_path)
        return final_path

    def get_duration(self, video_path: str | Path) -> float:
        """Return duration of a media file in seconds."""
        cmd = [
            self.ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(video_path),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe falhou ao obter duração: {result.stderr.strip()}"
            )
        return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Whisper Adapter
# ---------------------------------------------------------------------------

_SRT_NEWLINE = "\n"


def _format_timestamp_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_to_srt(segments: list) -> str:
    """Convert faster-whisper segments to SRT format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_srt(seg.start)
        end = _format_timestamp_srt(seg.end)
        text = seg.text.strip()
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return _SRT_NEWLINE.join(lines)


class WhisperAdapter:
    """Local audio transcription via faster-whisper.

    Falls back gracefully with clear error if faster-whisper is not installed.
    """

    def __init__(self, model_size: str = "base", language: str | None = None):
        self.model_size = model_size
        # None => auto-detect. A configured language (e.g. "pt") skips
        # detection, which matters most on short or ambiguous audio where
        # auto-detect is least reliable.
        self.language = language
        self._model = None

    def _load_model(self):
        """Lazy-load the Whisper model (heavy, ~1GB for base)."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper não encontrado. Instale com:\n"
                "  pip install faster-whisper\n"
                "Ou para GPU:\n"
                "  pip install faster-whisper[cuda]"
            )

        log.info("Carregando modelo whisper '%s' ...", self.model_size)
        # int8 on CPU: meaningfully faster and lighter than the float32
        # default, with negligible accuracy loss for this pipeline's use
        # (transcript text feeding a downstream extraction pass, not a
        # verbatim-critical transcript).
        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe_to_srt(self, audio_path: str | Path, output_dir: str | Path) -> Path:
        """Transcribe audio file and save as SRT.

        Writes to a temp file and renames into place atomically, so a
        crash mid-transcription never leaves a truncated transcript.srt
        that a stage-cache check could mistake for a finished one.

        Returns path to the generated transcript.srt.
        """
        audio_path = Path(audio_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._load_model()

        log.info("Transcrevendo %s ...", audio_path.name)
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            beam_size=5,
            language=self.language,
        )

        segments = list(segments_iter)

        log.info(
            "Transcrição concluída: %.1fs de áudio, %d segmentos, idioma: %s",
            info.duration, len(segments), info.language,
        )

        srt_content = _segments_to_srt(segments)
        final_path = output_dir / "transcript.srt"
        tmp_path = output_dir / "transcript.srt.tmp"
        tmp_path.write_text(srt_content, encoding="utf-8")
        os.replace(tmp_path, final_path)

        return final_path

    def transcribe_to_text(self, audio_path: str | Path, output_dir: str | Path) -> tuple[Path, str]:
        """Transcribe and return both SRT path and plain text content."""
        srt_path = self.transcribe_to_srt(audio_path, output_dir)

        try:
            from book_to_skill.parsers.subtitle import strip_subtitle_markup
            raw_srt = srt_path.read_text(encoding="utf-8")
            plain_text = strip_subtitle_markup(raw_srt)
        except ImportError:
            plain_text = self._basic_srt_to_text(srt_path.read_text(encoding="utf-8"))

        return srt_path, plain_text

    @staticmethod
    def _basic_srt_to_text(srt_content: str) -> str:
        """Basic SRT to plain text without book_to_skill dependency."""
        lines = []
        for line in srt_content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.isdigit():
                continue
            if "-->" in stripped:
                continue
            lines.append(stripped)
        return "\n".join(lines)
