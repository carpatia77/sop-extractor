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
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _HAS_EMBEDDINGS = True
except ImportError:
    _HAS_EMBEDDINGS = False

# Default model — small, fast, good quality
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_THRESHOLD = 0.55

# In-memory cache: model_name → loaded model
_model_cache: dict[str, object] = {}

# In-memory cache: sf_hash → embeddings array
_embeddings_cache: dict[str, np.ndarray] = {}


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
    except Exception:
        return None


def _sf_hash(sf: dict) -> str:
    """Deterministic hash of SF nodes for cache key."""
    nodes = sf.get("nodes", [])
    key = json.dumps(
        [(n.get("id", ""), n.get("statement", ""), n.get("term", ""))
         for n in nodes],
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _compute_embeddings(
    texts: list[str],
    model_name: str = DEFAULT_MODEL,
) -> np.ndarray | None:
    """Compute embeddings for a list of texts. Returns None if unavailable."""
    model = _get_model(model_name)
    if model is None:
        return None
    try:
        return model.encode(texts, convert_to_numpy=True)
    except Exception:
        return None


def embed_sf(
    sf: dict,
    model_name: str = DEFAULT_MODEL,
) -> np.ndarray | None:
    """Pre-compute embeddings for all SF nodes. Returns None if unavailable.

    Results are cached in-memory by SF hash.
    """
    h = _sf_hash(sf)
    if h in _embeddings_cache:
        return _embeddings_cache[h]

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

    emb = _compute_embeddings(texts, model_name)
    if emb is not None:
        _embeddings_cache[h] = emb
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
    except Exception:
        return []

    # Cosine similarity (manual, no sklearn dependency)
    # Normalize and dot product
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


def is_available() -> bool:
    """Check if embedding layer is available."""
    return _HAS_EMBEDDINGS and _get_model() is not None
