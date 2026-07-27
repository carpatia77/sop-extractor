#!/usr/bin/env python3
"""SF Embeddings Matcher — Camada 4: semantic similarity via embeddings.

Optional layer on top of sf_matcher's existing 3 layers (exact ID, substring,
salient-term Jaccard). Uses sentence-transformers for cosine similarity matching.

Fallback behavior:
  - If sentence-transformers is NOT installed → returns empty (layers 1-3 suffice)
  - If model fails to load → returns empty
  - If embeddings are not cached → computes on first call, caches in-memory

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
    """Get from embeddings cache."""
    return _embeddings_cache.get(key)


def _cache_put(key: str, emb: object, meta: dict) -> None:
    """Put into embeddings cache with FIFO eviction."""
    if len(_embeddings_cache) >= _MAX_CACHE:
        # Evict oldest entry
        oldest_key = next(iter(_embeddings_cache))
        del _embeddings_cache[oldest_key]
    _embeddings_cache[key] = (emb, meta)


def get_cache_metadata(sf: dict, model_name: str = DEFAULT_MODEL) -> dict | None:
    """Get provenance metadata for cached embeddings.

    Returns dict with model, dim, computed_at, count — or None if not cached.
    """
    h = _sf_hash(sf, model_name)
    cached = _cache_get(h)
    if cached is None:
        return None
    return cached[1].copy()


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
) -> object | None:
    """Pre-compute embeddings for all SF nodes. Returns None if unavailable.

    Results are cached in-memory by SF hash + model name.
    Cache includes provenance metadata (model, dim, timestamp).
    """
    h = _sf_hash(sf, model_name)
    cached = _cache_get(h)
    if cached is not None:
        emb, meta = cached
        # Validate dim: if model changed upstream, dim may diverge.
        # Use property lookup (zero inference) instead of encode(["probe"]).
        model = _get_model(model_name)
        if model is not None:
            try:
                expected_dim = model.get_embedding_dimension()
            except Exception:
                expected_dim = meta.get("dim")  # Can't check, trust cache
            if meta.get("dim") != expected_dim:
                log.warning(
                    "Cache dim mismatch: cached=%s, expected=%s — recomputing",
                    meta.get("dim"), expected_dim,
                )
                _embeddings_cache.pop(h, None)
                # Fall through to recompute
            else:
                return emb
        else:
            return emb

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
    _cache_put(h, emb, meta)
    return emb


def match_by_embedding(
    query: str,
    sf: dict,
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_MODEL,
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

    sf_emb = embed_sf(sf, model_name)
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
