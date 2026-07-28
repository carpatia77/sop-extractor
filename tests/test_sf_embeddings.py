#!/usr/bin/env python3
"""Tests for scripts/chavruta/sf_embeddings.py — Camada 4 embedding matcher.

Tests cover:
  - Fallback behavior (embeddings unavailable)
  - Mock-based tests for cache keys, cosine math, threshold, alignment
  - Integration with sf_matcher (layers 1-3 still work)
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sf_with_nodes():
    return {
        "nodes": [
            {
                "id": "concept:vd",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance due to variance",
                "statement": "Volatility drag reduces compounded returns",
            },
            {
                "id": "principle:snapshots",
                "type": "principle",
                "statement": "The system processes 100 snapshots per second",
                "epistemic_status": "certain",
            },
            {
                "id": "concept:memory",
                "type": "concept",
                "term": "Memory Usage",
                "definition": "RAM consumption by the application",
                "statement": "High memory usage causes swapping",
            },
        ],
        "edges": [],
    }


@pytest.fixture
def sf_different_definition():
    """Same IDs and terms, but different definitions — must produce different hash."""
    return {
        "nodes": [
            {
                "id": "concept:vd",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Completely different definition here",
                "statement": "Volatility drag reduces compounded returns",
            },
            {
                "id": "principle:snapshots",
                "type": "principle",
                "statement": "The system processes 100 snapshots per second",
                "epistemic_status": "certain",
            },
            {
                "id": "concept:memory",
                "type": "concept",
                "term": "Memory Usage",
                "definition": "Also a different definition",
                "statement": "High memory usage causes swapping",
            },
        ],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Fallback behavior (no embeddings)
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    def test_is_installed_false_when_not_installed(self):
        from chavruta.sf_embeddings import _HAS_EMBEDDINGS
        if not _HAS_EMBEDDINGS:
            from chavruta.sf_embeddings import is_installed
            assert is_installed() is False

    def test_match_by_embedding_empty_when_unavailable(self, sf_with_nodes):
        from chavruta.sf_embeddings import match_by_embedding, _HAS_EMBEDDINGS
        if not _HAS_EMBEDDINGS:
            result = match_by_embedding("volatility drag", sf_with_nodes)
            assert result == []

    def test_embed_sf_returns_none_when_unavailable(self, sf_with_nodes):
        from chavruta.sf_embeddings import embed_sf, _HAS_EMBEDDINGS
        if not _HAS_EMBEDDINGS:
            result = embed_sf(sf_with_nodes)
            assert result is None


# ---------------------------------------------------------------------------
# Cache key tests (bugs #2 and #3)
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_model_name_included_in_hash(self, sf_with_nodes):
        """Bug #2: same SF + different model → different hash."""
        from chavruta.sf_embeddings import _sf_hash
        h1 = _sf_hash(sf_with_nodes, "model-a")
        h2 = _sf_hash(sf_with_nodes, "model-b")
        assert h1 != h2

    def test_definition_included_in_hash(self, sf_with_nodes, sf_different_definition):
        """Bug #3: same IDs/terms + different definition → different hash."""
        from chavruta.sf_embeddings import _sf_hash
        h1 = _sf_hash(sf_with_nodes, "model-a")
        h2 = _sf_hash(sf_different_definition, "model-a")
        assert h1 != h2

    def test_identical_sf_same_hash(self, sf_with_nodes):
        from chavruta.sf_embeddings import _sf_hash
        h1 = _sf_hash(sf_with_nodes, "model-a")
        h2 = _sf_hash(sf_with_nodes, "model-a")
        assert h1 == h2


# ---------------------------------------------------------------------------
# Cache eviction tests (#6)
# ---------------------------------------------------------------------------

class TestCacheEviction:
    def test_cache_maxsize_enforced(self):
        from chavruta.sf_embeddings import _cache_put, _cache_get, _embeddings_cache, _MAX_CACHE
        _embeddings_cache.clear()
        for i in range(_MAX_CACHE + 2):
            _cache_put(f"key_{i}", f"emb_{i}", {"n": i})
        assert len(_embeddings_cache) == _MAX_CACHE
        # Oldest keys evicted
        assert _cache_get("key_0") is None
        assert _cache_get("key_1") is None
        # Newest keys retained
        assert _cache_get(f"key_{_MAX_CACHE + 1}") is not None

    def test_get_cache_metadata_returns_none_when_not_cached(self, sf_with_nodes):
        from chavruta.sf_embeddings import get_cache_metadata, _embeddings_cache
        _embeddings_cache.clear()
        result = get_cache_metadata(sf_with_nodes, "nonexistent_model")
        assert result is None

    def test_get_cache_metadata_returns_provenance(self, sf_with_nodes):
        from chavruta.sf_embeddings import _cache_put, _embeddings_cache, get_cache_metadata, _sf_hash
        _embeddings_cache.clear()
        h = _sf_hash(sf_with_nodes, "test_model")
        _cache_put(h, "fake_emb", {"model": "test_model", "dim": 384, "computed_at": "now"})
        meta = get_cache_metadata(sf_with_nodes, "test_model")
        assert meta is not None
        assert meta["model"] == "test_model"
        assert meta["dim"] == 384


# ---------------------------------------------------------------------------
# Mock-based tests (#4)
# ---------------------------------------------------------------------------

class TestWithMockModel:
    """Tests using mock embeddings to cover cosine math, threshold, alignment."""

    @pytest.fixture
    def mock_embeddings(self):
        """Mock _compute_embeddings to return deterministic vectors."""
        import numpy as np
        # 3 nodes → 3x3 identity-like matrix (orthogonal vectors)
        # Node 0: [1, 0, 0], Node 1: [0, 1, 0], Node 2: [0, 0, 1]
        fake_emb = np.eye(3, dtype=float)

        def fake_compute(texts, model_name="test"):
            meta = {"model": model_name, "dim": 3, "computed_at": "test", "count": len(texts)}
            return fake_emb, meta
        return fake_compute

    def test_cosine_similarity_orthogonal(self, sf_with_nodes, mock_embeddings, tmp_path):
        """Orthogonal vectors → similarity ~0 for non-matching queries."""
        import numpy as np
        with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=mock_embeddings):
            with patch("chavruta.sf_embeddings._HAS_EMBEDDINGS", True):
                with patch("chavruta.sf_embeddings._get_model") as mock_model:
                    # Mock model.encode to return [1,0,0] for any query
                    mock_model.return_value.encode.return_value = np.array([[1.0, 0.0, 0.0]])
                    from chavruta.sf_embeddings import match_by_embedding
                    result = match_by_embedding("anything", sf_with_nodes, threshold=0.5, cache_dir=tmp_path)
                    # Query [1,0,0] matches node 0 [1,0,0] with sim=1.0
                    # Others are orthogonal → sim=0
                    assert len(result) == 1
                    assert result[0][0]["id"] == "concept:vd"
                    assert result[0][1] == 1.0

    def test_threshold_filters_low_scores(self, sf_with_nodes, mock_embeddings, tmp_path):
        """Nodes below threshold are excluded."""
        import numpy as np
        with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=mock_embeddings):
            with patch("chavruta.sf_embeddings._HAS_EMBEDDINGS", True):
                with patch("chavruta.sf_embeddings._get_model") as mock_model:
                    # Query that's partially similar to all nodes
                    mock_model.return_value.encode.return_value = np.array([[0.5, 0.5, 0.0]])
                    from chavruta.sf_embeddings import match_by_embedding
                    # With threshold 0.8, partial matches excluded
                    result = match_by_embedding("partial", sf_with_nodes, threshold=0.8, cache_dir=tmp_path)
                    assert len(result) == 0
                    # With threshold 0.4, partial matches included
                    result = match_by_embedding("partial", sf_with_nodes, threshold=0.4, cache_dir=tmp_path)
                    assert len(result) >= 1

    def test_results_sorted_by_score(self, sf_with_nodes, mock_embeddings, tmp_path):
        """Results must be sorted by similarity descending."""
        import numpy as np
        with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=mock_embeddings):
            with patch("chavruta.sf_embeddings._HAS_EMBEDDINGS", True):
                with patch("chavruta.sf_embeddings._get_model") as mock_model:
                    # Query closer to node 1 than node 0
                    mock_model.return_value.encode.return_value = np.array([[0.1, 0.9, 0.0]])
                    from chavruta.sf_embeddings import match_by_embedding
                    result = match_by_embedding("test", sf_with_nodes, threshold=0.0, cache_dir=tmp_path)
                    scores = [s for _, s in result]
                    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Integration with sf_matcher (layers 1-3 still work)
# ---------------------------------------------------------------------------

class TestMatcherIntegration:
    def test_find_nodes_exact_id(self, sf_with_nodes):
        from chavruta.sf_matcher import find_nodes
        result = find_nodes("concept:vd", sf_with_nodes)
        assert len(result) == 1
        assert result[0]["id"] == "concept:vd"

    def test_find_nodes_substring(self, sf_with_nodes):
        from chavruta.sf_matcher import find_nodes
        result = find_nodes("Volatility Drag", sf_with_nodes)
        assert len(result) >= 1
        assert any(n["id"] == "concept:vd" for n in result)

    def test_find_nodes_salient(self, sf_with_nodes):
        from chavruta.sf_matcher import find_nodes
        result = find_nodes("compounded returns variance", sf_with_nodes)
        assert len(result) >= 1
        assert any(n["id"] == "concept:vd" for n in result)

    def test_find_best_match_returns_layer(self, sf_with_nodes):
        from chavruta.sf_matcher import find_best_match
        node, layer = find_best_match("concept:vd", sf_with_nodes)
        assert node is not None
        assert layer == "id"

    def test_find_best_match_no_match(self):
        from chavruta.sf_matcher import find_best_match
        sf = {"nodes": [{"id": "x", "term": "foo", "statement": "bar"}], "edges": []}
        node, layer = find_best_match("zzz_nonexistent_zzz", sf)
        assert node is None
        assert layer == "none"

    def test_matcher_imports_work(self):
        from chavruta.sf_matcher import find_nodes, find_best_match
        assert callable(find_nodes)
        assert callable(find_best_match)


# ---------------------------------------------------------------------------
# Disk cache tests
# ---------------------------------------------------------------------------

_HasEmbeddings = None  # Lazy check


def _has_embeddings():
    global _HasEmbeddings
    if _HasEmbeddings is None:
        try:
            from chavruta.sf_embeddings import _HAS_EMBEDDINGS
            _HasEmbeddings = _HAS_EMBEDDINGS
        except Exception:
            _HasEmbeddings = False
    return _HasEmbeddings


@pytest.mark.skipif(not _has_embeddings(), reason="sentence-transformers not installed")
class TestDiskCache:
    """Tests for the 2-tier cache (in-memory + disk).

    All tests use tmp_path to avoid polluting $HOME.
    """

    def test_disk_cache_write_and_read(self, sf_with_nodes, tmp_path):
        """Embeddings should persist to disk and be loadable."""
        from chavruta.sf_embeddings import (
            _sf_hash, _disk_put, _disk_get, DEFAULT_MODEL,
        )
        import numpy as np

        h = _sf_hash(sf_with_nodes, DEFAULT_MODEL)
        emb = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]])
        meta = {"model": DEFAULT_MODEL, "dim": 3, "count": 3}

        _disk_put(h, emb, meta, tmp_path)
        loaded = _disk_get(h, tmp_path)

        assert loaded is not None
        loaded_emb, loaded_meta = loaded
        np.testing.assert_array_almost_equal(loaded_emb, emb)
        assert loaded_meta["dim"] == 3
        assert loaded_meta["count"] == 3

    def test_disk_cache_miss_returns_none(self, tmp_path):
        """Disk cache miss should return None."""
        from chavruta.sf_embeddings import _disk_get
        assert _disk_get("nonexistent_key", tmp_path) is None

    def test_embed_sf_uses_disk_cache(self, sf_with_nodes, tmp_path):
        """embed_sf should store to and load from disk cache."""
        from chavruta.sf_embeddings import embed_sf, _sf_hash, _disk_get, DEFAULT_MODEL

        # First call: compute + store to disk
        emb1 = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert emb1 is not None

        # Verify disk file exists
        h = _sf_hash(sf_with_nodes, DEFAULT_MODEL)
        disk = _disk_get(h, tmp_path)
        assert disk is not None
        assert disk[1]["model"] == DEFAULT_MODEL

    def test_embed_sf_loads_from_disk(self, sf_with_nodes, tmp_path):
        """Second call should load from disk, not recompute."""
        from chavruta.sf_embeddings import embed_sf, _sf_hash, _disk_put, DEFAULT_MODEL
        import numpy as np

        # Pre-populate disk cache
        h = _sf_hash(sf_with_nodes, DEFAULT_MODEL)
        emb = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        meta = {"model": DEFAULT_MODEL, "dim": 2, "count": 3}
        _disk_put(h, emb, meta, tmp_path)

        # Clear in-memory cache to force disk read
        from chavruta.sf_embeddings import _embeddings_cache
        _embeddings_cache.clear()

        # Should load from disk
        loaded = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert loaded is not None

    def test_clear_disk_cache(self, sf_with_nodes, tmp_path):
        """clear_disk_cache should remove all cached files."""
        from chavruta.sf_embeddings import (
            embed_sf, clear_disk_cache, disk_cache_size, _embeddings_cache, DEFAULT_MODEL,
        )

        _embeddings_cache.clear()
        embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert disk_cache_size(tmp_path) >= 1

        removed = clear_disk_cache(tmp_path)
        assert removed >= 2  # .npy + .json
        assert disk_cache_size(tmp_path) == 0

    def test_disk_cache_survives_memory_clear(self, sf_with_nodes, tmp_path):
        """Embeddings should survive in-memory cache clear via disk."""
        from chavruta.sf_embeddings import (
            embed_sf, _embeddings_cache, DEFAULT_MODEL,
        )

        # Compute and cache
        emb1 = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert emb1 is not None

        # Clear in-memory cache
        _embeddings_cache.clear()

        # Should reload from disk (no recomputation)
        emb2 = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert emb2 is not None

    def test_disk_cache_dim_mismatch_recomputes(self, sf_with_nodes, tmp_path):
        """Disk cache with wrong dim should trigger recomputation."""
        from chavruta.sf_embeddings import (
            embed_sf, _disk_put, _sf_hash, _embeddings_cache, DEFAULT_MODEL,
        )
        import numpy as np

        # Pre-populate disk with wrong dim
        h = _sf_hash(sf_with_nodes, DEFAULT_MODEL)
        emb = np.array([[0.1, 0.2, 0.3, 0.4, 0.5]])  # dim=5, wrong
        meta = {"model": DEFAULT_MODEL, "dim": 5, "count": 1}
        _disk_put(h, emb, meta, tmp_path)
        _embeddings_cache.clear()

        # Should recompute (dim mismatch)
        loaded = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert loaded is not None
        # New embeddings should have correct dim (384 for MiniLM)
        assert loaded.shape[1] == 384

    def test_match_by_embedding_uses_disk_cache(self, sf_with_nodes, tmp_path):
        """match_by_embedding should work with disk cache."""
        from chavruta.sf_embeddings import match_by_embedding

        matches = match_by_embedding(
            "volatility drag", sf_with_nodes,
            threshold=0.30, cache_dir=tmp_path,
        )
        # Should find concept:vd via embeddings
        assert len(matches) >= 1

    def test_get_cache_metadata_checks_disk(self, sf_with_nodes, tmp_path):
        """get_cache_metadata should find entries on disk."""
        from chavruta.sf_embeddings import (
            embed_sf, _sf_hash, _disk_get, _embeddings_cache, DEFAULT_MODEL,
        )

        # Clear all caches to force compute + disk write
        _embeddings_cache.clear()
        emb = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)
        assert emb is not None

        # Verify it's on disk
        h = _sf_hash(sf_with_nodes, DEFAULT_MODEL)
        disk = _disk_get(h, tmp_path)
        assert disk is not None
        assert disk[1]["model"] == DEFAULT_MODEL

    def test_dim_mismatch_triggers_recompute(self, sf_with_nodes, tmp_path):
        """When cached dim ≠ model dim, embed_sf must recompute (not trust cache).

        This tests the get_embedding_dimension() code path — critical because
        get_sentence_embedding_dimension() is deprecated and must not regress.
        """
        from unittest.mock import patch, MagicMock
        from chavruta.sf_embeddings import (
            embed_sf, _disk_put, _sf_hash, _embeddings_cache, DEFAULT_MODEL,
        )
        import numpy as np

        # Pre-populate disk cache with dim=5 (wrong — model outputs 384)
        h = _sf_hash(sf_with_nodes, DEFAULT_MODEL)
        wrong_emb = np.zeros((3, 5))
        wrong_meta = {"model": DEFAULT_MODEL, "dim": 5, "count": 3}
        _disk_put(h, wrong_emb, wrong_meta, tmp_path)
        _embeddings_cache.clear()

        # Mock model whose get_embedding_dimension() returns 384 (correct)
        mock_model = MagicMock()
        mock_model.get_embedding_dimension.return_value = 384

        # Mock compute to return correct-dim embeddings
        correct_emb = np.zeros((3, 384))

        def fake_compute(texts, model_name="test"):
            return correct_emb, {"model": model_name, "dim": 384, "count": len(texts)}

        with patch("chavruta.sf_embeddings._get_model", return_value=mock_model):
            with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=fake_compute):
                loaded = embed_sf(sf_with_nodes, DEFAULT_MODEL, tmp_path)

        # Should have recomputed (dim mismatch detected)
        assert loaded is not None
        assert loaded.shape == (3, 384)  # correct dim, not 5
