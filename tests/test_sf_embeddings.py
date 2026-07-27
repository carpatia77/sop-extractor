#!/usr/bin/env python3
"""Tests for scripts/chavruta/sf_embeddings.py — Camada 4 embedding matcher.

Tests fallback behavior (embeddings unavailable) and integration with sf_matcher.
"""
import os
import sys
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


# ---------------------------------------------------------------------------
# Fallback behavior (no embeddings)
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    def test_is_available_returns_false_when_not_installed(self):
        from chavruta.sf_embeddings import _HAS_EMBEDDINGS
        # If sentence-transformers not installed, should be False
        # If installed, this test is skipped conceptually
        if not _HAS_EMBEDDINGS:
            from chavruta.sf_embeddings import is_available
            assert is_available() is False

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
        """sf_matcher should import cleanly even without embeddings."""
        from chavruta.sf_matcher import find_nodes, find_best_match
        assert callable(find_nodes)
        assert callable(find_best_match)
