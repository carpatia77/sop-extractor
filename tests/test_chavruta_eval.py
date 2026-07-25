#!/usr/bin/env python3
"""Tests for Chavruta eval harness — anti-hallucination, depth accuracy,
drift detection, refutation integration, no silent reconciliation.

These tests validate the CONTRACTUAL behavior of the Chavruta system
before the Engine itself is implemented. They test the building blocks
(sf_matcher, drift_detector, depth_tracker concepts) against fixtures
that represent the expected behavior.
"""
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.sf_matcher import find_nodes, find_best_match
from chavruta.drift_detector import detect_drift, is_drift
from evidence_ledger import build_ledger, get_evidence_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sf_with_refutation():
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
                "strongest_alternative": "Rebalancing can capture volatility harvesting premium",
                "disconfirming_evidence": "Would be false if Sharpe ratio were path-independent",
                "dissent_type": "qualifies",
            },
            {
                "id": "principle:nobody-knows",
                "type": "principle",
                "statement": "Nobody knows what the outcome of a single trade will be",
                "epistemic_status": "certain",
                "source_file": "test.txt",
                "evidence_id": "ev-def456",
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
            {"id": "edge:0001", "type": "used_in", "source": "concept:volatility-drag", "target": "sop:build-portfolio", "inferred": True},
        ],
    }


@pytest.fixture
def task_contract():
    return {"user_goal": "Understand volatility drag and its impact on portfolio returns"}


# ---------------------------------------------------------------------------
# Eval 1: Anti-hallucination — Chavruta must not assert outside SF
# ---------------------------------------------------------------------------

class TestAntiHallucination:
    def test_claim_in_sf_is_not_drift(self, sf_with_refutation, task_contract):
        """Claim that exists in SF should NOT be flagged as drift."""
        result = detect_drift(
            "Volatility drag compounds against you",
            sf_with_refutation, task_contract,
        )
        assert result["is_drift"] is False

    def test_claim_not_in_sf_is_drift(self, sf_with_refutation, task_contract):
        """Claim that does NOT exist in SF should be flagged."""
        result = detect_drift(
            "The Federal Reserve will raise rates tomorrow",
            sf_with_refutation, task_contract,
        )
        assert result["is_drift"] is True

    def test_partial_match_not_drift(self, sf_with_refutation, task_contract):
        """Partial overlap with SF should not be drift if anchored."""
        result = detect_drift(
            "Volatility drag impact on returns",
            sf_with_refutation, task_contract,
        )
        assert result["is_drift"] is False


# ---------------------------------------------------------------------------
# Eval 2: Depth accuracy — depth grounded in graph events
# NOTE: Depth tracker itself is implemented in Fase C. These tests verify
# that the building blocks (sf_matcher) can support depth determination.
# ---------------------------------------------------------------------------

class TestDepthAccuracy:
    def test_depth3_disconfirming_evidence(self, sf_with_refutation):
        """sf_matcher can find nodes referenced in disconfirming_evidence."""
        node, layer = find_best_match("volatility drag compounds", sf_with_refutation)
        assert node is not None
        assert node.get("disconfirming_evidence") is not None

    def test_depth4_crosses_concepts(self, sf_with_refutation):
        """sf_matcher finds multiple nodes when query spans concepts."""
        nodes = find_nodes("volatility drag", sf_with_refutation)
        assert len(nodes) >= 1
        sop_nodes = find_nodes("Build Portfolio", sf_with_refutation)
        assert len(sop_nodes) >= 1

    def test_depth5_invokes_alternative(self, sf_with_refutation):
        """sf_matcher can locate nodes with strongest_alternative."""
        node, layer = find_best_match("volatility drag compounds", sf_with_refutation)
        assert node is not None
        assert "rebalancing" in node.get("strongest_alternative", "").lower()


# ---------------------------------------------------------------------------
# Eval 3: Drift detection — no false negatives
# ---------------------------------------------------------------------------

class TestDriftDetection:
    def test_cooking_is_drift(self, sf_with_refutation):
        """Clearly unrelated topic must be drift."""
        assert is_drift("The recipe requires two cups of flour and sugar", sf_with_refutation) is True

    def test_weather_is_drift(self, sf_with_refutation):
        """Weather is unrelated to finance."""
        assert is_drift("It will rain tomorrow with 80% chance", sf_with_refutation) is True

    def test_volatility_is_not_drift(self, sf_with_refutation, task_contract):
        """Volatility-related content should not be drift."""
        assert is_drift("Volatility drag compounds returns", sf_with_refutation, task_contract) is False

    def test_rebalancing_is_not_drift(self, sf_with_refutation):
        """Rebalancing is in strongest_alternative — anchored."""
        result = detect_drift("Rebalancing can mitigate drag", sf_with_refutation)
        assert result["is_drift"] is False
        assert result["anchor_used"] == "strongest_alternative"


# ---------------------------------------------------------------------------
# Eval 4: Refutation integration — SF nodes carry refutation data
# ---------------------------------------------------------------------------

class TestRefutationIntegration:
    def test_principle_has_strongest_alternative(self, sf_with_refutation):
        """Principle nodes should carry strongest_alternative."""
        nodes = find_nodes("volatility drag compounds", sf_with_refutation)
        assert len(nodes) >= 1
        node = nodes[0]
        assert "strongest_alternative" in node
        assert "Rebalancing" in node["strongest_alternative"]

    def test_principle_has_disconfirming_evidence(self, sf_with_refutation):
        """Principle nodes should carry disconfirming_evidence."""
        nodes = find_nodes("volatility drag compounds", sf_with_refutation)
        node = nodes[0]
        assert "disconfirming_evidence" in node
        assert "Sharpe" in node["disconfirming_evidence"]

    def test_principle_has_dissent_type(self, sf_with_refutation):
        """Principle nodes should carry dissent_type."""
        nodes = find_nodes("volatility drag compounds", sf_with_refutation)
        node = nodes[0]
        assert node.get("dissent_type") == "qualifies"


# ---------------------------------------------------------------------------
# Eval 5: No silent reconciliation — contradictions surfaced
# ---------------------------------------------------------------------------

class TestNoSilentReconciliation:
    def test_contradiction_with_negation_is_drift(self, sf_with_refutation):
        """Response that NEGATES a principle must be flagged as contradiction."""
        result = detect_drift(
            "Volatility drag does NOT compound and is irrelevant",
            sf_with_refutation,
        )
        assert result["is_drift"] is True
        assert result["is_contradiction"] is True
        assert result["anchor_used"] == "none"

    def test_contradiction_with_challenge_words(self, sf_with_refutation):
        """Response that uses challenge words (wrong, myth) must be flagged."""
        result = detect_drift(
            "The author's principle about volatility drag is wrong",
            sf_with_refutation,
        )
        assert result["is_drift"] is True
        assert result["is_contradiction"] is True

    def test_contradiction_disconfirming_evidence(self, sf_with_refutation):
        """Response matching disconfirming_evidence is a challenge, not anchor."""
        result = detect_drift(
            "Sharpe ratio is path-independent so drag doesn't apply",
            sf_with_refutation,
        )
        # This matches the disconfirming_evidence of the principle
        assert result["is_contradiction"] is True

    def test_contradiction_overrides_anchor(self, sf_with_refutation):
        """Even with high coverage, contradiction forces drift."""
        result = detect_drift(
            "Volatility drag does not compound against you over time",
            sf_with_refutation,
        )
        assert result["is_drift"] is True
        assert result["is_contradiction"] is True
        # Must NOT be anchored despite high lexical overlap
        assert result["anchor_used"] == "none"

    def test_qualification_surfaced(self, sf_with_refutation):
        """Qualifying language without negation should use the refutation chain."""
        result = detect_drift(
            "Rebalancing can mitigate volatility drag",
            sf_with_refutation,
        )
        assert result["is_drift"] is False
        assert result["anchor_used"] == "strongest_alternative"
        assert result["is_contradiction"] is False

    def test_affirmation_not_contradiction(self, sf_with_refutation):
        """Affirming a principle is not a contradiction."""
        result = detect_drift(
            "Volatility drag compounds against you over time",
            sf_with_refutation,
        )
        assert result["is_drift"] is False
        assert result["is_contradiction"] is False


# ---------------------------------------------------------------------------
# Eval 6: Evidence Ledger integration
# ---------------------------------------------------------------------------

class TestEvidenceLedgerIntegration:
    def test_ledger_provides_evidence_text(self):
        """Evidence Ledger should provide evidence_text for claims."""
        principles = [
            {
                "statement": "Volatility drag compounds",
                "evidence": "Author states drag compounds at 12:34",
                "epistemic_status": "certain",
            }
        ]
        ledger = build_ledger(principles, "test.srt", "hash")
        text = get_evidence_text(ledger, "Volatility drag compounds")
        assert "12:34" in text

    def test_ledger_entry_has_required_fields(self):
        """Each ledger entry should have entry_id, claim, evidence_text."""
        principles = [
            {"statement": "Test claim", "evidence": "Test evidence", "epistemic_status": "certain"}
        ]
        ledger = build_ledger(principles, "test.txt", "hash")
        entry = ledger["entries"][0]
        assert entry["entry_id"].startswith("ev-")
        assert entry["claim"] == "Test claim"
        assert entry["evidence_text"] == "Test evidence"
