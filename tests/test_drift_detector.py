#!/usr/bin/env python3
"""Tests for scripts/chavruta/drift_detector.py — drift detection.

Tests: drift detection, anchor activation, edge cases, integration with sf_matcher.
"""
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.drift_detector import detect_drift, is_drift


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
                "strongest_alternative": "Rebalancing can mitigate volatility drag",
            },
            {
                "id": "sop:build-portfolio",
                "type": "sop",
                "name": "Build Portfolio",
                "when_to_use": "When investing in volatile assets",
                "source_file": "test.txt",
            },
        ],
        "edges": [],
    }


@pytest.fixture
def sample_task_contract():
    return {"user_goal": "Understand volatility drag and its impact on returns"}


# ---------------------------------------------------------------------------
# Basic drift detection
# ---------------------------------------------------------------------------

class TestDetectDrift:
    def test_no_drift_when_in_scope(self, sample_sf, sample_task_contract):
        result = detect_drift(
            "Volatility drag compounds against you",
            sample_sf, sample_task_contract,
        )
        assert result["is_drift"] is False

    def test_drift_when_out_of_scope(self, sample_sf, sample_task_contract):
        result = detect_drift(
            "The weather today is sunny and warm with clear skies",
            sample_sf, sample_task_contract,
        )
        assert result["is_drift"] is True

    def test_returns_confidence(self, sample_sf, sample_task_contract):
        result = detect_drift("test", sample_sf, sample_task_contract)
        assert "confidence" in result
        assert 0 <= result["confidence"] <= 1

    def test_returns_reason(self, sample_sf, sample_task_contract):
        result = detect_drift("test", sample_sf, sample_task_contract)
        assert "reason" in result
        assert len(result["reason"]) > 0

    def test_returns_matched_nodes(self, sample_sf, sample_task_contract):
        result = detect_drift("volatility", sample_sf, sample_task_contract)
        assert "matched_nodes" in result
        assert isinstance(result["matched_nodes"], list)

    def test_returns_anchor_used(self, sample_sf, sample_task_contract):
        result = detect_drift("test", sample_sf, sample_task_contract)
        assert "anchor_used" in result


# ---------------------------------------------------------------------------
# Anchor activation
# ---------------------------------------------------------------------------

class TestAnchorActivation:
    def test_strongest_alternative_anchor(self, sample_sf):
        result = detect_drift(
            "Rebalancing can mitigate volatility drag",
            sample_sf, None,
        )
        assert result["is_drift"] is False
        assert result["anchor_used"] == "strongest_alternative"

    def test_user_goal_anchor(self, sample_sf):
        # Use a response that doesn't overlap with strongest_alternative
        # ("Rebalancing can mitigate volatility drag")
        contract = {"user_goal": "Understand portfolio variance"}
        result = detect_drift(
            "Portfolio variance affects long-term returns",
            sample_sf, contract,
        )
        assert result["is_drift"] is False
        assert result["anchor_used"] == "user_goal"

    def test_no_anchor_needed_when_in_sf(self, sample_sf):
        result = detect_drift(
            "Volatility drag compounds over time",
            sample_sf, None,
        )
        assert result["is_drift"] is False

    def test_drift_when_no_anchor(self, sample_sf):
        result = detect_drift(
            "The recipe calls for two cups of flour",
            sample_sf, None,
        )
        assert result["is_drift"] is True
        assert result["anchor_used"] == "none"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_response(self, sample_sf):
        result = detect_drift("", sample_sf)
        assert result["is_drift"] is False
        assert "too short" in result["reason"].lower()

    def test_empty_sf(self):
        result = detect_drift("anything at all", {"nodes": [], "edges": []})
        assert result["is_drift"] is True

    def test_no_task_contract(self, sample_sf):
        result = detect_drift("volatility drag", sample_sf, None)
        assert result["is_drift"] is False

    def test_custom_threshold(self, sample_sf):
        result_lenient = detect_drift("volatility", sample_sf, None, match_threshold=0.1)
        # Lenient threshold should not flag as drift
        assert result_lenient["is_drift"] is False


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------

class TestContradictionDetection:
    def test_negation_flagged(self, sample_sf):
        """Response with negation words targeting SF terms is contradiction."""
        result = detect_drift(
            "Volatility drag does NOT compound", sample_sf,
        )
        assert result["is_drift"] is True
        assert result["is_contradiction"] is True

    def test_challenge_words_flagged(self, sample_sf):
        """Response with challenge words (wrong, myth) is contradiction."""
        result = detect_drift(
            "The principle about volatility drag is wrong", sample_sf,
        )
        assert result["is_contradiction"] is True

    def test_negation_overrides_anchor(self, sample_sf):
        """Negation forces drift even with high coverage."""
        result = detect_drift(
            "Volatility drag does not compound against you over time", sample_sf,
        )
        assert result["is_drift"] is True
        assert result["anchor_used"] == "none"

    def test_affirmation_not_contradiction(self, sample_sf):
        """Affirming SF content is not contradiction."""
        result = detect_drift(
            "Volatility drag compounds against you", sample_sf,
        )
        assert result["is_contradiction"] is False

    def test_disagree_is_challenge(self, sample_sf):
        """'disagree' should be detected as challenge word."""
        result = detect_drift(
            "I disagree — volatility drag actually helps returns", sample_sf,
        )
        assert result["is_contradiction"] is True

    def test_out_of_scope_not_contradiction(self, sample_sf):
        """Unrelated content is drift but not contradiction."""
        result = detect_drift(
            "The weather is sunny today", sample_sf,
        )
        assert result["is_drift"] is True
        assert result["is_contradiction"] is False


# ---------------------------------------------------------------------------
# Boolean wrapper
# ---------------------------------------------------------------------------

class TestIsDrift:
    def test_returns_bool(self, sample_sf):
        assert isinstance(is_drift("test", sample_sf), bool)

    def test_no_drift(self, sample_sf):
        assert is_drift("volatility drag compounds", sample_sf) is False

    def test_drift(self, sample_sf):
        assert is_drift("cooking recipe with flour", sample_sf) is True
