"""Media adapters — wrappers for yt-dlp, ffmpeg, and faster-whisper.

Each adapter encapsulates one external tool, handles binary detection,
and raises clear Portuguese error messages on failure.

Scope note: ffmpeg is ONLY for local video files. For URLs, yt-dlp
handles audio extraction internally via -x flag.
"""
from __future__ import annotations

import json
import logging
import random
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)


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
# yt-dlp Adapter — with anti-ban measures
# ---------------------------------------------------------------------------

# Realistic browser user-agents for request spoofing
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Minimum delay between consecutive requests (seconds)
_MIN_DELAY = 2.0
# Maximum additional random jitter (seconds)
_MAX_JITTER = 3.0
# Max retries on transient failures
_MAX_RETRIES = 3
# Base delay for exponential backoff (seconds)
_BACKOFF_BASE = 5.0


class YtDlpAdapter:
    """Download videos and extract metadata via yt-dlp.

    Includes anti-ban measures: user-agent spoofing, rate limiting,
    retry with exponential backoff, and random jitter.
    """

    def __init__(self):
        self.binary = self._find_binary()
        self._last_request_time = 0.0

    def _find_binary(self) -> str:
        return _find_binary("yt-dlp")

    def _rate_limit(self):
        """Enforce minimum delay between requests with random jitter."""
        now = time.time()
        elapsed = now - self._last_request_time
        delay = _MIN_DELAY + random.uniform(0, _MAX_JITTER)
        if elapsed < delay:
            sleep_time = delay - elapsed
            log.debug("Rate limit: aguardando %.1fs", sleep_time)
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _get_user_agent(self) -> str:
        """Return a random user-agent string."""
        return random.choice(_USER_AGENTS)

    def _run_with_retry(self, cmd: list, timeout: int = 120) -> subprocess.CompletedProcess:
        """Run a subprocess with retry + exponential backoff."""
        last_error = None
        for attempt in range(_MAX_RETRIES):
            try:
                self._rate_limit()
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout
                )
                if result.returncode == 0:
                    return result
                # Non-zero returncode — check if retryable
                stderr = result.stderr.strip().lower()
                retryable = any(kw in stderr for kw in [
                    "http error 429", "too many requests",
                    "http error 503", "service unavailable",
                    "http error 403", "forbidden",
                    "timed out", "timeout",
                    "connection reset", "connection refused",
                ])
                if retryable and attempt < _MAX_RETRIES - 1:
                    backoff = _BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 2)
                    log.warning(
                        "yt-dlp erro retryável (tentativa %d/%d), aguardando %.0fs: %s",
                        attempt + 1, _MAX_RETRIES, backoff, result.stderr.strip()[:200],
                    )
                    time.sleep(backoff)
                    last_error = result
                    continue
                # Non-retryable or last attempt
                return result
            except subprocess.TimeoutExpired:
                if attempt < _MAX_RETRIES - 1:
                    backoff = _BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "yt-dlp timeout (tentativa %d/%d), aguardando %.0fs",
                        attempt + 1, _MAX_RETRIES, backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise RuntimeError(
                    f"yt-dlp timeout após {_MAX_RETRIES} tentativas"
                )
        # Should not reach here, but safety fallback
        if last_error is not None:
            return last_error
        raise RuntimeError("yt-dlp falhou após múltiplas tentativas")

    @staticmethod
    def is_url(source: str) -> bool:
        """Return True if source looks like a URL."""
        lower = source.lower()
        return lower.startswith("http://") or lower.startswith("https://")

    def get_info(self, url: str) -> dict:
        """Extract video metadata including canonical video-ID.

        Returns dict with keys: id, title, uploader, upload_date, duration.
        """
        cmd = [
            self.binary,
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--user-agent", self._get_user_agent(),
            url,
        ]
        result = self._run_with_retry(cmd, timeout=120)
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
        """Download audio-only from a URL.

        Uses yt-dlp -x which internally calls ffmpeg for extraction.
        Returns the path to the downloaded audio file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_template = str(output_dir / "audio.%(ext)s")
        cmd = [
            self.binary,
            "-x",                          # extract audio
            "--audio-format", "mp3",
            "--audio-quality", "2",
            "-o", output_template,
            "--no-playlist",
            "--user-agent", self._get_user_agent(),
            url,
        ]
        log.info("Baixando áudio de %s ...", url)
        result = self._run_with_retry(cmd, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(
                f"yt-dlp falhou ao baixar áudio: {result.stderr.strip()}"
            )

        audio_files = list(output_dir.glob("audio.*"))
        if not audio_files:
            raise FileNotFoundError(
                "yt-dlp não gerou arquivo de áudio. Verifique a URL."
            )
        return audio_files[0]


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
        """Extract audio track from a LOCAL video file as MP3."""
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "audio.mp3"
        cmd = [
            self.ffmpeg,
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            "-y",
            str(output_path),
        ]
        log.info("Extraindo áudio de %s ...", video_path.name)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg falhou ao extrair áudio: {result.stderr[-500:]}"
            )
        return output_path

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

# SRT formatting constants
_SRT_NEWLINE = "\n"


def _format_timestamp_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = round((seconds - int(seconds)) * 1000)
    if millis >= 1000:
        millis = 999
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

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
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
        self._model = WhisperModel(self.model_size, device="cpu")

    def transcribe_to_srt(self, audio_path: str | Path, output_dir: str | Path) -> Path:
        """Transcribe audio file and save as SRT.

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
            language=None,
        )

        segments = list(segments_iter)

        log.info(
            "Transcrição concluída: %.1fs de áudio, %d segmentos, idioma: %s",
            info.duration, len(segments), info.language,
        )

        srt_content = _segments_to_srt(segments)
        srt_path = output_dir / "transcript.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        return srt_path

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
