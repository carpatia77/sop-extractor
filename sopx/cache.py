"""Cache Manager — hash-based dedup to prevent reprocessing.

Two key strategies:
- URL: sha256 of the canonical video-ID (from yt-dlp info["id"]),
  NOT the raw URL — prevents duplicates from youtu.be vs youtube.com.
- File: sha256("abspath:size:mtime_ns") — no full-file read.

Stage-aware: audio and SRT are cached separately, so a whisper crash
doesn't force re-download of the audio. A stage is only considered done
once a ".done" sentinel is written *after* the artifact is fully in
place — a directory that merely exists-and-is-non-empty is not proof of
completion, since a crash mid-write (partial audio.mp3, truncated
transcript.srt) leaves exactly that state. Callers must write stage
artifacts atomically (temp file + os.replace) and call mark_stage_done()
only once the artifact is verified complete.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

DEFAULT_CACHE_DIR = Path("~/.config/sopx/cache").expanduser()

_DONE_SENTINEL = ".done"


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
            with open(self._index_path, "r", encoding="utf-8") as f:
                self._index = json.load(f)
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
        """Return the directory for a cached stage artifact.

        Stages: 'audio', 'srt'
        """
        stage_dir = self.cache_dir / key / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        return stage_dir

    def mark_stage_done(self, key: str, stage: str) -> None:
        """Write the completion sentinel for a stage. Call this only after
        the stage's artifact file(s) are fully and atomically in place."""
        stage_dir = self.stage_path(key, stage)
        (stage_dir / _DONE_SENTINEL).write_text(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), encoding="utf-8"
        )

    def is_stage_done(self, key: str, stage: str) -> bool:
        """Check if a specific stage completed successfully (sentinel
        present) — not merely that its directory is non-empty, which a
        crash mid-write would also satisfy."""
        stage_dir = self.cache_dir / key / stage
        return (stage_dir / _DONE_SENTINEL).exists()

    # -- High-level interface ---------------------------------------------

    def is_done(self, key: str) -> bool:
        """Check if a source has been fully processed (all stages) AND its
        recorded output directory still exists on disk — an index entry
        whose output_dir was deleted out-of-band must not report a hit."""
        entry = self._index.get(key)
        if not entry:
            return False
        output_dir = entry.get("output_dir")
        return bool(output_dir) and Path(output_dir).exists()

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
