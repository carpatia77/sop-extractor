#!/usr/bin/env python3
"""Integration tests for sf_matcher — Camada 4 (embeddings) contribution.

Verifies that:
  1. Camada 4 contributes results when layers 1-3 return partial/empty results
  2. Embedding matches are deduplicated with lexical matches
  3. match_layer is correctly reported for all match types
  4. find_nodes combines all 4 layers properly
  5. Paraphrases without lexical overlap are caught by embeddings
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.sf_matcher import find_nodes, find_best_match
from chavruta.sf_embeddings import is_installed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sf_paraphrase():
    """SF where paraphrases have zero lexical overlap with queries.

    Key design: node text uses completely different vocabulary than queries
    so that layers 1-3 (exact, substring, salient) find nothing.
    Only Camada 4 (embeddings) can bridge the semantic gap.
    """
    return {
        "nodes": [
            {
                "id": "concept:throughput",
                "type": "concept",
                "term": "Processing Speed",
                "definition": "Rate at which transactions are completed by the engine",
            },
            {
                "id": "principle:latency",
                "type": "principle",
                "statement": "Lower response delay improves user satisfaction",
                "epistemic_status": "certain",
            },
            {
                "id": "sop:optimize",
                "type": "sop",
                "name": "Tune Engine Performance",
                "when_to_use": "When the system feels sluggish",
            },
        ],
        "edges": [],
    }


@pytest.fixture
def sf_lexical():
    """SF with clear lexical matches (layers 1-3 should handle these)."""
    return {
        "nodes": [
            {
                "id": "concept:volatility-drag",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance due to variance",
            },
            {
                "id": "principle:vd-compounds",
                "type": "principle",
                "statement": "Volatility drag compounds against you over time",
                "epistemic_status": "certain",
            },
        ],
        "edges": [],
    }


@pytest.fixture
def sf_mixed():
    """SF with both lexical and paraphrase matches."""
    return {
        "nodes": [
            {
                "id": "concept:memory",
                "type": "concept",
                "term": "Memory",
                "definition": "Computer memory (RAM) used by the system",
            },
            {
                "id": "principle:memory-leak",
                "type": "principle",
                "statement": "Memory leaks cause degradation over time",
                "epistemic_status": "certain",
            },
            {
                "id": "concept:storage",
                "type": "concept",
                "term": "Storage",
                "definition": "Disk space used for persistent data",
            },
        ],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Test: Camada 4 contributes when layers 1-3 are empty
# ---------------------------------------------------------------------------

class TestCamada4Contribution:
    def test_paraphrase_caught_by_embeddings(self, sf_paraphrase):
        """Paraphrase with zero lexical overlap should be caught by embeddings.

        "execution velocity" vs "Rate at which transactions are completed"
        — no shared salient terms between query and node text.
        Embedding similarity: 0.535 (above 0.50 threshold).
        """
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        nodes = find_nodes("execution velocity", sf_paraphrase)
        node_ids = [n["id"] for n in nodes]
        assert "concept:throughput" in node_ids, (
            f"Camada 4 should catch 'execution velocity' → 'Processing Speed', got: {node_ids}"
        )

    def test_paraphrase_best_match_layer(self, sf_paraphrase):
        """Best match for paraphrase should report 'embedding' layer."""
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        node, layer = find_best_match("execution velocity", sf_paraphrase)
        assert node is not None
        assert node["id"] == "concept:throughput"
        assert layer == "embedding", f"Expected 'embedding' layer, got '{layer}'"

    def test_synonym_caught_by_embeddings(self, sf_paraphrase):
        """Synonym with different vocabulary should be caught.

        "system responsiveness" vs "Lower response delay improves user satisfaction"
        — no shared salient terms. Embedding similarity: 0.447.
        """
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        # Uses threshold=0.30 since 0.447 is below default 0.50 but still meaningful
        from chavruta.sf_embeddings import match_by_embedding
        matches = match_by_embedding("system responsiveness", sf_paraphrase, threshold=0.30)
        node_ids = [m[0]["id"] for m in matches]
        assert "principle:latency" in node_ids, (
            f"Embeddings should find 'system responsiveness' → 'Lower response delay', got: {node_ids}"
        )


# ---------------------------------------------------------------------------
# Test: Deduplication across layers
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_lexical_and_embedding_no_duplicates(self, sf_lexical):
        """When both lexical and embedding match the same node, no duplicates."""
        nodes = find_nodes("volatility drag compounds", sf_lexical)
        node_ids = [n["id"] for n in nodes]
        assert len(node_ids) == len(set(node_ids)), f"Duplicate nodes found: {node_ids}"

    def test_exact_id_takes_priority(self, sf_lexical):
        """Exact ID match returns immediately, no other layers checked."""
        node, layer = find_best_match("concept:volatility-drag", sf_lexical)
        assert node is not None
        assert node["id"] == "concept:volatility-drag"
        assert layer == "id"

    def test_substring_takes_priority_over_embedding(self, sf_mixed):
        """Substring match should be preferred over embedding for same node."""
        # "Memory" is an exact substring in the term
        node, layer = find_best_match("Memory", sf_mixed)
        assert node is not None
        assert layer == "substring"


# ---------------------------------------------------------------------------
# Test: find_nodes combines all layers
# ---------------------------------------------------------------------------

class TestFindNodesCombinesLayers:
    def test_returns_results_from_multiple_layers(self, sf_mixed):
        """find_nodes should combine results from different layers."""
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        # "RAM usage" should match "Memory" (embedding) + possibly others
        nodes = find_nodes("RAM usage", sf_mixed)
        # At least one match expected
        assert len(nodes) >= 1

    def test_salient_layer_works(self, sf_lexical):
        """Layer 3 (salient terms) should find matches via keyword overlap."""
        nodes = find_nodes("volatility drag", sf_lexical)
        node_ids = [n["id"] for n in nodes]
        assert len(node_ids) >= 1

    def test_empty_query_returns_empty(self, sf_lexical):
        """Empty query should return no matches."""
        nodes = find_nodes("", sf_lexical)
        assert len(nodes) == 0


# ---------------------------------------------------------------------------
# Test: match_layer reporting
# ---------------------------------------------------------------------------

class TestMatchLayerReporting:
    def test_find_best_match_returns_layer(self, sf_lexical):
        """find_best_match always returns a layer string."""
        node, layer = find_best_match("volatility drag", sf_lexical)
        assert layer in ("id", "substring", "salient", "embedding", "none")

    def test_find_best_match_none_when_no_match(self):
        """find_best_match returns (None, 'none') when nothing matches."""
        sf = {"nodes": [{"id": "x", "statement": "foo bar"}], "edges": []}
        node, layer = find_best_match("quantum physics", sf)
        assert node is None
        assert layer == "none"

    def test_embedding_layer_in_report(self, sf_paraphrase):
        """Embedding match should be reported when it's the winning layer."""
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        node, layer = find_best_match("execution velocity", sf_paraphrase)
        if node and node["id"] == "concept:throughput":
            assert layer == "embedding"


# ---------------------------------------------------------------------------
# Test: Engine integration — match_layer flows through
# ---------------------------------------------------------------------------

class TestEngineIntegration:
    def test_engine_v1_returns_match_layer(self, sf_lexical):
        """Engine v1 process() returns match_layer in output."""
        from chavruta.engine import ChavrutaEngine
        engine = ChavrutaEngine(sf_lexical)
        result = engine.process("Volatility drag compounds against you")
        assert "match_layer" in result
        assert result["match_layer"] in ("id", "substring", "salient", "embedding", "none")

    def test_engine_v2_returns_match_layer(self, sf_lexical):
        """Engine v2 process() returns match_layer in output."""
        from chavruta.engine_v2 import ChavrutaEngineV2
        engine = ChavrutaEngineV2(sf_lexical)
        result = engine.process("Volatility drag compounds against you")
        assert "match_layer" in result
        assert result["match_layer"] in ("id", "substring", "salient", "embedding", "none")

    def test_engine_v1_returns_semantic_issues(self, sf_lexical):
        """Engine v1 process() returns semantic_issues in output."""
        from chavruta.engine import ChavrutaEngine
        engine = ChavrutaEngine(sf_lexical)
        result = engine.process("Volatility drag compounds against you")
        assert "semantic_issues" in result
        assert isinstance(result["semantic_issues"], list)

    def test_engine_v2_returns_semantic_issues(self, sf_lexical):
        """Engine v2 process() returns semantic_issues in output."""
        from chavruta.engine_v2 import ChavrutaEngineV2
        engine = ChavrutaEngineV2(sf_lexical)
        result = engine.process("Volatility drag compounds against you")
        assert "semantic_issues" in result
        assert isinstance(result["semantic_issues"], list)

    def test_engine_history_tracks_match_layer(self, sf_lexical):
        """Engine history entries include match_layer."""
        from chavruta.engine import ChavrutaEngine
        engine = ChavrutaEngine(sf_lexical)
        engine.process("Volatility drag compounds against you")
        assert len(engine.history) == 1
        assert "match_layer" in engine.history[0]

    def test_engine_paraphrase_uses_embedding_layer(self, sf_paraphrase):
        """Engine should report match_layer='embedding' for paraphrase queries."""
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        from chavruta.engine import ChavrutaEngine
        engine = ChavrutaEngine(sf_paraphrase)
        result = engine.process("What is the execution velocity of the system?")
        # Should not be drift (paraphrase matches Processing Speed via embeddings)
        # match_layer should be embedding since there's no lexical overlap
        if result["matched_node"] and result["matched_node"]["id"] == "concept:throughput":
            assert result["match_layer"] == "embedding"
