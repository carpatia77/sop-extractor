#!/usr/bin/env python3
"""Tests for scripts/chavruta/sf_embeddings.py — Camada 4 embedding matcher.

Tests cover:
  - Fallback behavior (embeddings unavailable)
  - Mock-based tests for cache keys, cosine math, threshold, alignment
  - Integration with sf_matcher (layers 1-3 still work)
"""
import os
import sys
from unittest.mock import patch, MagicMock

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

    def test_cosine_similarity_orthogonal(self, sf_with_nodes, mock_embeddings):
        """Orthogonal vectors → similarity ~0 for non-matching queries."""
        import numpy as np
        with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=mock_embeddings):
            with patch("chavruta.sf_embeddings._HAS_EMBEDDINGS", True):
                with patch("chavruta.sf_embeddings._get_model") as mock_model:
                    # Mock model.encode to return [1,0,0] for any query
                    mock_model.return_value.encode.return_value = np.array([[1.0, 0.0, 0.0]])
                    from chavruta.sf_embeddings import match_by_embedding
                    result = match_by_embedding("anything", sf_with_nodes, threshold=0.5)
                    # Query [1,0,0] matches node 0 [1,0,0] with sim=1.0
                    # Others are orthogonal → sim=0
                    assert len(result) == 1
                    assert result[0][0]["id"] == "concept:vd"
                    assert result[0][1] == 1.0

    def test_threshold_filters_low_scores(self, sf_with_nodes, mock_embeddings):
        """Nodes below threshold are excluded."""
        import numpy as np
        with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=mock_embeddings):
            with patch("chavruta.sf_embeddings._HAS_EMBEDDINGS", True):
                with patch("chavruta.sf_embeddings._get_model") as mock_model:
                    # Query that's partially similar to all nodes
                    mock_model.return_value.encode.return_value = np.array([[0.5, 0.5, 0.0]])
                    from chavruta.sf_embeddings import match_by_embedding
                    # With threshold 0.8, partial matches excluded
                    result = match_by_embedding("partial", sf_with_nodes, threshold=0.8)
                    assert len(result) == 0
                    # With threshold 0.4, partial matches included
                    result = match_by_embedding("partial", sf_with_nodes, threshold=0.4)
                    assert len(result) >= 1

    def test_results_sorted_by_score(self, sf_with_nodes, mock_embeddings):
        """Results must be sorted by similarity descending."""
        import numpy as np
        with patch("chavruta.sf_embeddings._compute_embeddings", side_effect=mock_embeddings):
            with patch("chavruta.sf_embeddings._HAS_EMBEDDINGS", True):
                with patch("chavruta.sf_embeddings._get_model") as mock_model:
                    # Query closer to node 1 than node 0
                    mock_model.return_value.encode.return_value = np.array([[0.1, 0.9, 0.0]])
                    from chavruta.sf_embeddings import match_by_embedding
                    result = match_by_embedding("test", sf_with_nodes, threshold=0.0)
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
