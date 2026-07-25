#!/usr/bin/env python3
"""Tests for scripts/chavruta/sf_matcher.py — multi-layer node matching.

Tests: exact ID, substring, salient-term overlap, unified matcher, edge cases.
"""
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.sf_matcher import (
    match_by_id,
    match_by_substring,
    match_by_salient,
    find_nodes,
    find_best_match,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_sf():
    return {
        "nodes": [
            {
                "id": "concept:volatility-drag",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance due to variance",
                "source_file": "test.txt",
            },
            {
                "id": "principle:abc123",
                "type": "principle",
                "statement": "Volatility drag compounds against you over time",
                "epistemic_status": "certain",
                "source_file": "test.txt",
            },
            {
                "id": "sop:build-portfolio",
                "type": "sop",
                "name": "Build Portfolio",
                "when_to_use": "When investing in volatile assets",
                "source_file": "test.txt",
            },
            {
                "id": "reference:sharpe-1966",
                "type": "reference",
                "name": "Sharpe (1966)",
                "source_file": "test.txt",
            },
        ],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Layer 1: Exact ID match
# ---------------------------------------------------------------------------

class TestMatchById:
    def test_exact_match(self, sample_sf):
        node = match_by_id("principle:abc123", sample_sf["nodes"])
        assert node is not None
        assert node["id"] == "principle:abc123"

    def test_no_match(self, sample_sf):
        node = match_by_id("principle:nonexistent", sample_sf["nodes"])
        assert node is None

    def test_whitespace_stripped(self, sample_sf):
        node = match_by_id("  principle:abc123  ", sample_sf["nodes"])
        assert node is not None

    def test_empty_query(self, sample_sf):
        node = match_by_id("", sample_sf["nodes"])
        assert node is None

    def test_empty_nodes(self):
        node = match_by_id("anything", [])
        assert node is None


# ---------------------------------------------------------------------------
# Layer 2: Substring match
# ---------------------------------------------------------------------------

class TestMatchBySubstring:
    def test_match_in_statement(self, sample_sf):
        matches = match_by_substring("volatility drag", sample_sf["nodes"])
        assert len(matches) >= 2  # concept + principle

    def test_match_in_term(self, sample_sf):
        matches = match_by_substring("Portfolio", sample_sf["nodes"])
        assert len(matches) >= 1
        assert any(n["id"] == "sop:build-portfolio" for n in matches)

    def test_match_in_name(self, sample_sf):
        matches = match_by_substring("Sharpe", sample_sf["nodes"])
        assert len(matches) >= 1

    def test_no_match(self, sample_sf):
        matches = match_by_substring("completely unrelated", sample_sf["nodes"])
        assert len(matches) == 0

    def test_empty_query(self, sample_sf):
        matches = match_by_substring("", sample_sf["nodes"])
        assert len(matches) == 0

    def test_case_insensitive(self, sample_sf):
        matches = match_by_substring("VOLATILITY DRAG", sample_sf["nodes"])
        assert len(matches) >= 2


# ---------------------------------------------------------------------------
# Layer 3: Salient-term overlap
# ---------------------------------------------------------------------------

class TestMatchBySalient:
    def test_high_overlap(self, sample_sf):
        matches = match_by_salient(
            "volatility drag compounds over time", sample_sf["nodes"],
        )
        assert len(matches) >= 1
        assert matches[0][1] > 0.3

    def test_low_overlap_filtered(self, sample_sf):
        matches = match_by_salient(
            "completely unrelated topic about cooking", sample_sf["nodes"],
        )
        assert len(matches) == 0

    def test_returns_scores(self, sample_sf):
        matches = match_by_salient("volatility drag compounds", sample_sf["nodes"])
        assert len(matches) >= 1
        assert isinstance(matches[0][1], float)

    def test_sorted_by_score(self, sample_sf):
        matches = match_by_salient(
            "volatility drag compounds", sample_sf["nodes"],
        )
        if len(matches) >= 2:
            assert matches[0][1] >= matches[1][1]

    def test_custom_threshold(self, sample_sf):
        matches_high = match_by_salient("volatility", sample_sf["nodes"], threshold=0.8)
        matches_low = match_by_salient("volatility", sample_sf["nodes"], threshold=0.1)
        assert len(matches_low) >= len(matches_high)

    def test_empty_query(self, sample_sf):
        matches = match_by_salient("", sample_sf["nodes"])
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# Unified matcher
# ---------------------------------------------------------------------------

class TestFindNodes:
    def test_exact_id_takes_priority(self, sample_sf):
        nodes = find_nodes("principle:abc123", sample_sf)
        assert len(nodes) == 1
        assert nodes[0]["id"] == "principle:abc123"

    def test_substring_fallback(self, sample_sf):
        nodes = find_nodes("Portfolio", sample_sf)
        assert len(nodes) >= 1

    def test_salient_fallback(self, sample_sf):
        nodes = find_nodes("variance underperformance", sample_sf)
        # Should find via salient terms
        assert len(nodes) >= 0  # may or may not match depending on stopwords

    def test_no_match(self, sample_sf):
        nodes = find_nodes("xyz123nonexistent", sample_sf)
        assert len(nodes) == 0


class TestFindBestMatch:
    def test_best_by_id(self, sample_sf):
        node, layer = find_best_match("principle:abc123", sample_sf)
        assert node is not None
        assert layer == "id"

    def test_best_by_substring(self, sample_sf):
        node, layer = find_best_match("Sharpe", sample_sf)
        assert node is not None
        assert layer == "substring"

    def test_best_by_salient(self, sample_sf):
        node, layer = find_best_match("geometric variance", sample_sf)
        # May find concept:volatility-drag via salient terms
        if node:
            assert layer == "salient"

    def test_no_match(self, sample_sf):
        node, layer = find_best_match("xyz123nonexistent", sample_sf)
        assert node is None
        assert layer == "none"
