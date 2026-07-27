#!/usr/bin/env python3
"""SF Embeddings Matcher — Camada 4: semantic similarity via embeddings.

Fallback layer on top of sf_matcher's existing 3 layers (exact ID, substring,
salient-term Jaccard). Uses sentence-transformers for cosine similarity matching.

Behavior:
  - If sentence-transformers is NOT installed → returns empty (layers 1-3 suffice)
  - If model fails to load → returns empty
  - Embeddings are cached in 2 tiers:
    1. In-memory (fast, FIFO eviction at 8 entries)
    2. Disk (persistent, survives restarts, at cache_dir/embeddings/)
  - Only fires when layers 1-3 return no results (conservative fallback)

This layer catches cases keyword matching misses:
  - Synonyms: "memory usage" vs "RAM consumption"
  - Paraphrases: "throughput" vs "processing speed"
  - Related concepts: "sword" vs "weapon"

Used by:
  - sf_matcher.py: find_nodes() and find_best_match()
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

_HAS_EMBEDDINGS = SentenceTransformer is not None and _HAS_NUMPY

# Default model — small, fast, good quality
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_THRESHOLD = 0.50  # Calibrated: catches synonyms (0.62+), rejects noise (<0.10)

# Default cache directory
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sopx" / "embeddings"

# In-memory cache: model_name → loaded model
_model_cache: dict[str, object] = {}

# In-memory cache: cache_key → (embeddings, metadata)
# Max 8 entries to prevent memory leak (FIFO eviction)
_MAX_CACHE = 8
_embeddings_cache: dict[str, tuple[object, dict]] = {}


def is_installed() -> bool:
    """Check if sentence-transformers is importable (cheap, no I/O)."""
    return _HAS_EMBEDDINGS


def is_model_loadable(model_name: str = DEFAULT_MODEL) -> bool:
    """Check if model can be loaded (expensive: may download ~80MB)."""
    return _get_model(model_name) is not None


def _get_model(model_name: str = DEFAULT_MODEL) -> object | None:
    """Load model (cached in memory). Returns None if unavailable."""
    if not _HAS_EMBEDDINGS:
        return None
    if model_name in _model_cache:
        return _model_cache[model_name]
    try:
        model = SentenceTransformer(model_name)
        _model_cache[model_name] = model
        return model
    except Exception as exc:
        log.warning("Failed to load embedding model %r: %s", model_name, exc)
        return None


def _sf_hash(sf: dict, model_name: str) -> str:
    """Deterministic hash of SF nodes for cache key.

    Includes all fields that go into the embedding text:
    id, statement, term, definition, name, when_to_use.
    Also includes model_name to prevent cross-model cache collision.
    """
    nodes = sf.get("nodes", [])
    key = json.dumps(
        [(n.get("id", ""), n.get("statement", ""), n.get("term", ""),
          n.get("definition", ""), n.get("name", ""), n.get("when_to_use", ""))
         for n in nodes],
        sort_keys=True, ensure_ascii=False,
    )
    combined = f"{model_name}::{key}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _cache_get(key: str) -> tuple[object, dict] | None:
    """Get from in-memory cache."""
    return _embeddings_cache.get(key)


def _cache_put(key: str, emb: object, meta: dict) -> None:
    """Put into in-memory cache with FIFO eviction."""
    if len(_embeddings_cache) >= _MAX_CACHE:
        # Evict oldest entry
        oldest_key = next(iter(_embeddings_cache))
        del _embeddings_cache[oldest_key]
    _embeddings_cache[key] = (emb, meta)


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

def _disk_cache_path(key: str, cache_dir: Path | None = None) -> Path:
    """Get disk cache path for a given key."""
    d = cache_dir or _DEFAULT_CACHE_DIR
    return d / f"{key}.npy"


def _disk_meta_path(key: str, cache_dir: Path | None = None) -> Path:
    """Get disk metadata path for a given key."""
    d = cache_dir or _DEFAULT_CACHE_DIR
    return d / f"{key}.json"


def _disk_get(key: str, cache_dir: Path | None = None) -> tuple[object, dict] | None:
    """Load embeddings from disk cache. Returns (numpy_array, metadata) or None.

    Returns None if sentence-transformers is not installed — cached embeddings
    are useless without the model to compute query embeddings.
    """
    if not _HAS_EMBEDDINGS:
        return None
    emb_path = _disk_cache_path(key, cache_dir)
    meta_path = _disk_meta_path(key, cache_dir)
    if not emb_path.exists() or not meta_path.exists():
        return None
    try:
        emb = np.load(emb_path)
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return emb, meta
    except Exception as exc:
        log.debug("Disk cache read failed for %s: %s", key, exc)
        return None


def _disk_put(key: str, emb: object, meta: dict, cache_dir: Path | None = None) -> None:
    """Save embeddings to disk cache."""
    if not _HAS_NUMPY:
        return
    d = cache_dir or _DEFAULT_CACHE_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / f"{key}.npy", emb)
        with open(d / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        log.debug("Disk cache write failed for %s: %s", key, exc)


def clear_disk_cache(cache_dir: Path | None = None) -> int:
    """Remove all disk-cached embeddings. Returns number of files removed."""
    d = cache_dir or _DEFAULT_CACHE_DIR
    if not d.exists():
        return 0
    count = 0
    for p in d.glob("*.npy"):
        p.unlink(missing_ok=True)
        count += 1
    for p in d.glob("*.json"):
        p.unlink(missing_ok=True)
        count += 1
    return count


def disk_cache_size(cache_dir: Path | None = None) -> int:
    """Return number of cached SFs on disk."""
    d = cache_dir or _DEFAULT_CACHE_DIR
    if not d.exists():
        return 0
    return len(list(d.glob("*.npy")))


def get_cache_metadata(sf: dict, model_name: str = DEFAULT_MODEL) -> dict | None:
    """Get provenance metadata for cached embeddings.

    Returns dict with model, dim, computed_at, count — or None if not cached.
    Checks in-memory first, then disk.
    """
    h = _sf_hash(sf, model_name)
    cached = _cache_get(h)
    if cached is not None:
        return cached[1].copy()
    disk = _disk_get(h)
    if disk is not None:
        return disk[1].copy()
    return None


def _compute_embeddings(
    texts: list[str],
    model_name: str = DEFAULT_MODEL,
) -> tuple[object, dict] | None:
    """Compute embeddings for a list of texts.

    Returns (embeddings_array, metadata_dict) or None if unavailable.
    Metadata includes model name, dimension, and computation timestamp.
    """
    model = _get_model(model_name)
    if model is None:
        return None
    try:
        emb = model.encode(texts, convert_to_numpy=True)
        meta = {
            "model": model_name,
            "dim": int(emb.shape[1]),
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "count": len(texts),
        }
        return emb, meta
    except Exception as exc:
        log.warning("Embedding computation failed for model %r: %s", model_name, exc)
        return None


def embed_sf(
    sf: dict,
    model_name: str = DEFAULT_MODEL,
    cache_dir: Path | None = None,
) -> object | None:
    """Pre-compute embeddings for all SF nodes. Returns None if unavailable.

    2-tier cache:
      1. In-memory (fast, FIFO eviction at 8 entries)
      2. Disk (persistent at cache_dir/embeddings/, survives restarts)

    Cache includes provenance metadata (model, dim, timestamp).
    """
    h = _sf_hash(sf, model_name)

    # Tier 1: in-memory
    cached = _cache_get(h)
    if cached is not None:
        emb, meta = cached
        # Validate dim: if model changed upstream, dim may diverge.
        model = _get_model(model_name)
        if model is not None:
            try:
                expected_dim = model.get_embedding_dimension()
            except Exception:
                expected_dim = meta.get("dim")
            if meta.get("dim") != expected_dim:
                log.warning(
                    "Cache dim mismatch: cached=%s, expected=%s — recomputing",
                    meta.get("dim"), expected_dim,
                )
                _embeddings_cache.pop(h, None)
            else:
                return emb
        else:
            return emb

    # Tier 2: disk (only if model can run)
    if _HAS_EMBEDDINGS:
        disk = _disk_get(h, cache_dir)
        if disk is not None:
            emb, meta = disk
            # Validate dim
            model = _get_model(model_name)
            if model is not None:
                try:
                    expected_dim = model.get_embedding_dimension()
                except Exception:
                    expected_dim = meta.get("dim")
                if meta.get("dim") != expected_dim:
                    log.warning(
                        "Disk cache dim mismatch: cached=%s, expected=%s — recomputing",
                        meta.get("dim"), expected_dim,
                    )
                else:
                    # Promote to in-memory cache
                    _cache_put(h, emb, meta)
                    return emb
            else:
                _cache_put(h, emb, meta)
                return emb

    # Tier 3: compute
    nodes = sf.get("nodes", [])
    if not nodes:
        return None

    texts = []
    for n in nodes:
        parts = [
            n.get("statement", ""),
            n.get("term", ""),
            n.get("definition", ""),
        ]
        texts.append(" ".join(p for p in parts if p).strip())

    result = _compute_embeddings(texts, model_name)
    if result is None:
        return None
    emb, meta = result

    # Store in both caches
    _cache_put(h, emb, meta)
    _disk_put(h, emb, meta, cache_dir)
    return emb


def match_by_embedding(
    query: str,
    sf: dict,
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_MODEL,
    cache_dir: Path | None = None,
) -> list[tuple[dict, float]]:
    """Match query against SF nodes using embedding cosine similarity.

    Returns list of (node, similarity_score) tuples, sorted by score descending.
    Only includes nodes with similarity > threshold.
    Returns empty list if embeddings are unavailable.
    """
    if not _HAS_EMBEDDINGS:
        return []

    nodes = sf.get("nodes", [])
    if not nodes:
        return []

    sf_emb = embed_sf(sf, model_name, cache_dir)
    if sf_emb is None:
        return []

    model = _get_model(model_name)
    if model is None:
        return []

    try:
        query_emb = model.encode([query], convert_to_numpy=True)
    except Exception as exc:
        log.warning("Query embedding failed: %s", exc)
        return []

    # Cosine similarity (manual, no sklearn dependency)
    query_norm = query_emb / (np.linalg.norm(query_emb, axis=1, keepdims=True) + 1e-8)
    sf_norms = sf_emb / (np.linalg.norm(sf_emb, axis=1, keepdims=True) + 1e-8)
    similarities = (query_norm @ sf_norms.T)[0]

    matches = []
    for i, sim in enumerate(similarities):
        score = float(sim)
        if score > threshold:
            matches.append((nodes[i], round(score, 3)))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches
