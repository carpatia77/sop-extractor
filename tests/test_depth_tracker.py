#!/usr/bin/env python3
"""Tests for scripts/chavruta/depth_tracker.py — grounded depth scoring.

Tests: each depth level (1-7), monotonicity, edge cases, depth bar.
"""
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.depth_tracker import (
    evaluate_depth,
    get_depth_label,
    depth_bar,
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
                "id": "principle:vd-compounds",
                "type": "principle",
                "statement": "Volatility drag compounds against you over time",
                "epistemic_status": "certain",
                "source_file": "test.txt",
                "evidence_id": "ev-abc123",
                "strongest_alternative": "Rebalancing can mitigate volatility drag",
                "disconfirming_evidence": "Would be false if Sharpe ratio were path-independent",
            },
            {
                "id": "principle:nobody-knows",
                "type": "principle",
                "statement": "Nobody knows what the outcome of a single trade will be",
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
        ],
        "edges": [
            {"id": "edge:0001", "type": "used_in", "source": "concept:volatility-drag", "target": "sop:build-portfolio"},
        ],
    }


# ---------------------------------------------------------------------------
# Depth levels
# ---------------------------------------------------------------------------

class TestDepthLevels:
    def test_depth_1_repeats_sf_terms(self, sample_sf):
        # "geometric" is in concept definition but concept has no evidence_id
        result = evaluate_depth("geometric", sample_sf)
        assert result["depth"] == 1

    def test_depth_2_references_node(self, sample_sf):
        result = evaluate_depth("volatility drag compounds against you over time", sample_sf)
        assert result["depth"] >= 2

    def test_depth_3_engages_disconfirming(self, sample_sf):
        result = evaluate_depth("Sharpe ratio path-independent", sample_sf)
        assert result["depth"] >= 3

    def test_depth_4_crosses_connected_nodes(self, sample_sf):
        """Natural phrase mentioning concept + connected SOP."""
        result = evaluate_depth(
            "Volatility drag matters when building a portfolio", sample_sf,
        )
        assert result["depth"] >= 4

    def test_depth_5_invokes_alternative(self, sample_sf):
        """Phrase invoking EXCLUSIVE alternative terms (rebalancing, harvesting)."""
        result = evaluate_depth(
            "Rebalancing mitigates drag by harvesting premium", sample_sf,
        )
        assert result["depth"] >= 5

    def test_depth_5_not_triggered_by_superficial_repetition(self, sample_sf):
        """Repeating principle vocabulary should NOT trigger depth 5."""
        result = evaluate_depth("volatility drag compounds", sample_sf)
        # Should NOT be depth 5 — just repetition, no evaluation
        assert result["scores"][5] is False

    def test_depth_7_uncertainty(self, sample_sf):
        result = evaluate_depth("não sei se volatility drag é sempre verdade", sample_sf)
        assert result["depth"] >= 7


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------

class TestMonotonicity:
    def test_max_rule(self, sample_sf):
        """depth = max(disparados), not sum or last."""
        # "Rebalancing mitigates drag by harvesting premium" → depth 5 (alternative) + depth 6 (new term anchored)
        result = evaluate_depth("Rebalancing mitigates drag by harvesting premium", sample_sf)
        assert result["depth"] == 6  # max(5, 6) = 6, not sum

    def test_empty_response(self, sample_sf):
        result = evaluate_depth("", sample_sf)
        assert result["depth"] == 1

    def test_no_match(self, sample_sf):
        result = evaluate_depth("xyz123nonexistent", sample_sf)
        # Should still get depth 1 if any SF term matches, else 1
        assert result["depth"] >= 1


# ---------------------------------------------------------------------------
# Labels and bars
# ---------------------------------------------------------------------------

class TestLabels:
    def test_all_depths_have_labels(self):
        for d in range(1, 8):
            label = get_depth_label(d)
            assert isinstance(label, str)
            assert len(label) > 0

    def test_depth_bar_format(self):
        bar = depth_bar(4)
        assert "4/7" in bar
        assert "█" in bar
        assert "░" in bar

    def test_depth_bar_width(self):
        bar = depth_bar(7, width=30)
        assert bar.count("█") == 30
        assert "7/7" in bar


# ---------------------------------------------------------------------------
# Scores dict
# ---------------------------------------------------------------------------

class TestScores:
    def test_scores_has_all_levels(self, sample_sf):
        result = evaluate_depth("volatility drag compounds", sample_sf)
        assert "scores" in result
        assert len(result["scores"]) == 7
        for d in range(1, 8):
            assert d in result["scores"]
            assert isinstance(result["scores"][d], bool)

    def test_depth_6_type(self, sample_sf):
        result = evaluate_depth("volatility drag", sample_sf)
        assert "depth_6_type" in result
        assert result["depth_6_type"] in ("creation", "none")
