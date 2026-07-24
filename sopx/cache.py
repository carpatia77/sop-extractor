"""Cache Manager — hash-based dedup to prevent reprocessing.

Two key strategies:
- URL: sha256 of the canonical video-ID (from yt-dlp info["id"]),
  NOT the raw URL — prevents duplicates from youtu.be vs youtube.com.
- File: sha256("abspath:size:mtime_ns") — no full-file read.

Stage-aware: audio and SRT are cached separately, so a whisper crash
doesn't force re-download of the audio.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

DEFAULT_CACHE_DIR = Path("~/.config/sopx/cache").expanduser()


class CacheManager:
    """Content-hash dedup cache for ingestion pipeline."""

    def __init__(self, cache_dir: str | Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.cache_dir / "index.json"
        self._index: dict = {}
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, ValueError):
                self._index = {}
        else:
            self._index = {}

    def _save(self) -> None:
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2, ensure_ascii=False)

    # -- Key strategies ---------------------------------------------------

    @staticmethod
    def key_for_url(canonical_id: str) -> str:
        """SHA256 of the canonical video-ID (not the raw URL)."""
        return hashlib.sha256(canonical_id.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def key_for_file(file_path: str | Path) -> str:
        """SHA256 of 'abspath:size:mtime_ns' — no full-file read."""
        p = Path(file_path).resolve()
        stat = p.stat()
        raw = f"{p}:{stat.st_size}:{int(stat.st_mtime_ns)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    # -- Stage-aware cache ------------------------------------------------

    def stage_path(self, key: str, stage: str) -> Path:
        """Return the path for a cached stage artifact.

        Stages: 'audio', 'srt'
        """
        stage_dir = self.cache_dir / key / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        return stage_dir

    def is_stage_done(self, key: str, stage: str) -> bool:
        """Check if a specific stage has been completed.

        Uses a .done sentinel file to ensure atomicity — a crash during
        writes leaves a partial dir without the sentinel, so retries
        re-process instead of serving corrupted artifacts.
        """
        stage_dir = self.cache_dir / key / stage
        return (stage_dir / ".done").exists()

    def mark_stage_done(self, key: str, stage: str) -> None:
        """Mark a stage as completed by writing a .done sentinel."""
        stage_dir = self.cache_dir / key / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / ".done").write_text("ok", encoding="utf-8")

    # -- High-level interface ---------------------------------------------

    def is_done(self, key: str) -> bool:
        """Check if a source has been fully processed (all stages).

        Revalidates that output_dir still exists — if the user deleted it,
        this returns False so the pipeline re-processes.
        """
        entry = self._index.get(key)
        if not entry:
            return False
        output_dir = entry.get("output_dir")
        if not output_dir:
            return False
        return Path(output_dir).exists()

    def mark_done(self, key: str, output_dir: str, **metadata) -> None:
        """Mark a source as fully processed and persist the index."""
        self._index[key] = {
            "output_dir": output_dir,
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **metadata,
        }
        self._save()

    def get_output_dir(self, key: str) -> str | None:
        """Return output directory path if already processed."""
        entry = self._index.get(key)
        if entry:
            return entry.get("output_dir")
        return None

    def entries(self) -> list[dict]:
        """Return all cache entries (for --status)."""
        result = []
        for key, entry in self._index.items():
            result.append({"key": key, **entry})
        return result

    def clear(self) -> int:
        """Clear the entire cache index. Returns number of entries removed."""
        count = len(self._index)
        self._index = {}
        self._save()
        return count
