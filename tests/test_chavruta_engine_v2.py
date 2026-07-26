#!/usr/bin/env python3
"""Tests for Chavruta Engine v2 — robust debate motor.

Tests: evidence citation, repetition detection, safety valve, session state.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.engine_v2 import ChavrutaEngineV2, _cite_evidence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sf():
    return {
        "nodes": [
            {
                "id": "concept:vd",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance due to variance",
                "source_file": "test.txt",
            },
            {
                "id": "principle:vd",
                "type": "principle",
                "statement": "Volatility drag compounds against you over time",
                "epistemic_status": "certain",
                "source_file": "test.txt",
                "evidence_id": "ev-abc123",
                "strongest_alternative": "Rebalancing can mitigate volatility drag",
                "disconfirming_evidence": "Would be false if Sharpe ratio were path-independent",
            },
            {
                "id": "sop:bp",
                "type": "sop",
                "name": "Build Portfolio",
                "when_to_use": "When investing in volatile assets",
                "source_file": "test.txt",
            },
        ],
        "edges": [
            {"id": "e1", "type": "used_in", "source": "concept:vd", "target": "sop:bp"},
        ],
    }


@pytest.fixture
def engine(sf):
    return ChavrutaEngineV2(sf)


# ---------------------------------------------------------------------------
# Evidence citation
# ---------------------------------------------------------------------------

class TestCiteEvidence:
    def test_cites_evidence_id(self):
        node = {"evidence_id": "ev-abc123", "epistemic_status": "certain"}
        citation = _cite_evidence(node)
        assert "ev-abc123" in citation
        assert "certain" in citation

    def test_cites_locator(self):
        node = {"evidence_id": "ev-abc123", "locator": "00:12:34-00:13:02"}
        citation = _cite_evidence(node)
        assert "00:12:34" in citation

    def test_empty_node(self):
        citation = _cite_evidence({})
        assert citation == ""


# ---------------------------------------------------------------------------
# Basic processing
# ---------------------------------------------------------------------------

class TestBasicProcessing:
    def test_returns_dict(self, engine):
        result = engine.process("Volatility drag compounds")
        assert isinstance(result, dict)

    def test_has_required_keys(self, engine):
        result = engine.process("test")
        for key in ["is_drift", "depth", "challenge", "depth_bar"]:
            assert key in result

    def test_increments_history(self, engine):
        engine.process("test")
        assert len(engine.history) == 1

    def test_updates_max_depth(self, engine):
        engine.process("volatility drag compounds")
        assert engine.max_depth_seen >= 1


# ---------------------------------------------------------------------------
# Drift handling
# ---------------------------------------------------------------------------

class TestDriftHandling:
    def test_drift_returns_warning(self, engine):
        result = engine.process("The weather is sunny")
        assert result["is_drift"] is True

    def test_drift_depth_zero(self, engine):
        result = engine.process("Cooking recipe")
        assert result["depth"] == 0


# ---------------------------------------------------------------------------
# Evidence citation in challenges
# ---------------------------------------------------------------------------

class TestEvidenceCitation:
    def test_contradiction_cites_evidence(self, engine):
        result = engine.process("Volatility drag does NOT compound")
        assert result["is_contradiction"] is True
        assert "ev-abc123" in result["challenge"]

    def test_depth_challenge_cites_evidence(self, engine):
        result = engine.process("volatility drag compounds")
        assert "ev-abc123" in result["challenge"] or "epistemic" in result["challenge"]


# ---------------------------------------------------------------------------
# Repetition detection
# ---------------------------------------------------------------------------

class TestRepetitionDetection:
    def test_no_repetition(self, engine):
        engine.process("volatility drag compounds")
        result = engine.process("volatility drag compounds")
        # Should not ask same question twice
        assert "já discutimos" in result["challenge"].lower() or "elabore" in result["challenge"].lower()

    def test_tracks_challenged_nodes(self, engine):
        engine.process("volatility drag compounds")
        assert len(engine.nodes_challenged) >= 1


# ---------------------------------------------------------------------------
# Safety valve
# ---------------------------------------------------------------------------

class TestSafetyValve:
    def test_fallback_asks_for_evidence(self, engine):
        # Response that doesn't match any node
        result = engine.process("something completely unrelated but anchored")
        if not result["is_drift"] and not result["is_contradiction"]:
            # If not drift/contradiction, should ask for evidence
            assert "evidência" in result["challenge"].lower() or "fonte" in result["challenge"].lower()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

class TestSessionState:
    def test_session_summary(self, engine):
        engine.process("volatility drag compounds")
        engine.process("The weather is sunny")
        summary = engine.get_session_summary()
        assert summary["total_moves"] == 2
        assert summary["max_depth"] >= 1

    def test_save_load_state(self, engine, tmp_path):
        engine.process("volatility drag compounds")
        state_path = str(tmp_path / "state.json")
        engine.save_state(state_path)

        engine2 = ChavrutaEngineV2(engine.sf)
        engine2.load_state(state_path)
        assert len(engine2.history) == 1
        assert engine2.max_depth_seen >= 1
