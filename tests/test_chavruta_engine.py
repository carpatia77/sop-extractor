#!/usr/bin/env python3
"""Tests for scripts/chavruta/engine.py — Chavruta debate motor.

Tests: engine initialization, process loop, depth challenges,
contradiction handling, session summary, drift handling.
"""
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.engine import ChavrutaEngine


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


@pytest.fixture
def engine(sample_sf):
    return ChavrutaEngine(sample_sf)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInitialization:
    def test_creates_engine(self, engine):
        assert engine is not None

    def test_empty_history(self, engine):
        assert len(engine.history) == 0

    def test_max_depth_zero(self, engine):
        assert engine.max_depth_seen == 0


# ---------------------------------------------------------------------------
# Process loop
# ---------------------------------------------------------------------------

class TestProcess:
    def test_returns_dict(self, engine):
        result = engine.process("Volatility drag compounds")
        assert isinstance(result, dict)

    def test_has_required_keys(self, engine):
        result = engine.process("test")
        assert "is_drift" in result
        assert "depth" in result
        assert "challenge" in result
        assert "depth_bar" in result

    def test_increments_history(self, engine):
        engine.process("Volatility drag compounds")
        assert len(engine.history) == 1

    def test_updates_max_depth(self, engine):
        engine.process("Volatility drag compounds")
        assert engine.max_depth_seen >= 1


# ---------------------------------------------------------------------------
# Drift handling
# ---------------------------------------------------------------------------

class TestDriftHandling:
    def test_drift_returns_warning(self, engine):
        result = engine.process("The weather is sunny today")
        assert result["is_drift"] is True
        assert "voltar" in result["challenge"].lower() or "fora" in result["challenge"].lower()

    def test_drift_depth_zero(self, engine):
        result = engine.process("Cooking recipe with flour")
        assert result["depth"] == 0


# ---------------------------------------------------------------------------
# Contradiction handling
# ---------------------------------------------------------------------------

class TestContradictionHandling:
    def test_contradiction_flagged(self, engine):
        result = engine.process("Volatility drag does NOT compound")
        assert result["is_contradiction"] is True

    def test_contradiction_challenge(self, engine):
        result = engine.process("Volatility drag is wrong")
        assert "contradiz" in result["challenge"].lower() or "evidência" in result["challenge"].lower()


# ---------------------------------------------------------------------------
# Depth challenges
# ---------------------------------------------------------------------------

class TestDepthChallenges:
    def test_depth_1_challenge(self, engine):
        result = engine.process("volatility")
        assert result["depth"] >= 1
        assert len(result["challenge"]) > 0

    def test_depth_3_challenge(self, engine):
        result = engine.process("Sharpe ratio path-independent")
        assert result["depth"] >= 3
        assert "?" in result["challenge"]

    def test_depth_4_no_crash(self, engine):
        """Depth 4 with both nodes matched should not crash."""
        # Phrase that genuinely matches concept + connected SOP
        result = engine.process("Volatility Drag Build Portfolio")
        # Should not raise IndexError or TypeError
        assert "challenge" in result
        assert len(result["challenge"]) > 0

    def test_depth_5_challenge(self, engine):
        result = engine.process(
            "Rebalancing mitigates drag by harvesting premium",
        )
        assert result["depth"] >= 5


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------

class TestSessionSummary:
    def test_empty_summary(self, engine):
        summary = engine.get_session_summary()
        assert summary["total_moves"] == 0

    def test_summary_after_moves(self, engine):
        engine.process("volatility drag compounds")
        engine.process("Sharpe ratio path-independent")
        summary = engine.get_session_summary()
        assert summary["total_moves"] == 2
        assert summary["max_depth"] >= 1

    def test_contradiction_count(self, engine):
        engine.process("Volatility drag does NOT compound")
        summary = engine.get_session_summary()
        assert summary["contradictions"] == 1


# ---------------------------------------------------------------------------
# Evidence ledger integration (anchor #3)
# ---------------------------------------------------------------------------

class TestEvidenceLedgerIntegration:
    def test_anchor_3_active(self, sample_sf):
        from evidence_ledger import build_ledger
        principles = [
            {"statement": "Volatility drag compounds", "evidence": "Author states drag compounds", "epistemic_status": "certain"}
        ]
        ledger = build_ledger(principles, "test.txt", "hash")
        engine = ChavrutaEngine(sample_sf, evidence_ledger=ledger)
        result = engine.process("Author states drag compounds")
        # Should be anchored via evidence_text
        assert result["anchor_used"] == "evidence_text" or result["depth"] >= 1
