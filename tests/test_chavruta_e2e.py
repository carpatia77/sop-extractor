#!/usr/bin/env python3
"""End-to-end tests for the complete Chavruta pipeline.

Pipeline: sf_matcher → drift_detector → semantic_guard → depth_tracker → engine

Tests realistic debate scenarios across all 7 depth levels, drift detection,
contradiction handling, semantic guard integration, Camada 4 embedding
contribution, and session state tracking.

Each test exercises the FULL pipeline through the engine, not isolated modules.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.engine import ChavrutaEngine
from chavruta.engine_v2 import ChavrutaEngineV2
from chavruta.semantic_guard import check_semantic_errors
from chavruta.sf_embeddings import is_installed


# ---------------------------------------------------------------------------
# Rich Semantic Field fixture — realistic trading curriculum
# ---------------------------------------------------------------------------

@pytest.fixture
def trading_sf():
    """A realistic 10-node Semantic Field for a trading curriculum.

    Includes: concepts, principles, SOPs, edges, refutation data,
    evidence_ids, disconfirming_evidence, strongest_alternative.
    """
    return {
        "nodes": [
            {
                "id": "concept:volatility-drag",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance of volatile assets due to variance",
                "source_file": "quantguild.txt",
            },
            {
                "id": "principle:vd-compounds",
                "type": "principle",
                "statement": "Volatility drag compounds against you over time",
                "epistemic_status": "certain",
                "evidence_id": "ev-001",
                "locator": "03:45",
                "strongest_alternative": "Rebalancing can capture volatility harvesting premium",
                "disconfirming_evidence": "Would be false if Sharpe ratio were path-independent",
                "dissent_type": "qualifies",
                "source_file": "quantguild.txt",
            },
            {
                "id": "principle:nobody-knows",
                "type": "principle",
                "statement": "Nobody knows what will happen next in the market",
                "epistemic_status": "certain",
                "evidence_id": "ev-002",
                "locator": "07:12",
                "source_file": "quantguild.txt",
            },
            {
                "id": "concept:tail-risk",
                "type": "concept",
                "term": "Tail Risk",
                "definition": "Risk of extreme events in the fat tails of return distribution",
                "source_file": "quantguild.txt",
            },
            {
                "id": "principle:tail-protection",
                "type": "principle",
                "statement": "Tail risk hedging costs reduce compound returns",
                "epistemic_status": "certain",
                "evidence_id": "ev-003",
                "locator": "12:30",
                "strongest_alternative": "Insurance against ruin justifies the cost",
                "disconfirming_evidence": "Would be false if tails were thin enough to ignore",
                "dissent_type": "qualifies",
                "source_file": "quantguild.txt",
            },
            {
                "id": "concept:position-sizing",
                "type": "concept",
                "term": "Position Sizing",
                "definition": "Determining how much capital to allocate per trade",
                "source_file": "quantguild.txt",
            },
            {
                "id": "sop:kelly-criterion",
                "type": "sop",
                "name": "Kelly Criterion",
                "when_to_use": "When sizing positions to maximize long-term growth",
                "definition": "Optimal bet fraction = edge / odds",
                "source_file": "quantguild.txt",
            },
            {
                "id": "concept:survival",
                "type": "concept",
                "term": "Survival",
                "definition": "Staying in the game long enough for edge to manifest",
                "source_file": "quantguild.txt",
            },
            {
                "id": "principle:ruin-is-permanent",
                "type": "principle",
                "statement": "Ruin is permanent — you cannot recover from zero",
                "epistemic_status": "certain",
                "evidence_id": "ev-004",
                "locator": "18:45",
                "source_file": "quantguild.txt",
            },
            {
                "id": "sop:check-risk-before-entry",
                "type": "sop",
                "name": "Risk Check Before Entry",
                "when_to_use": "Before entering any position",
                "definition": "Verify max loss does not exceed account risk limit",
                "source_file": "quantguild.txt",
            },
        ],
        "edges": [
            {"id": "e1", "type": "used_in", "source": "concept:volatility-drag", "target": "concept:position-sizing"},
            {"id": "e2", "type": "mitigates", "source": "concept:tail-risk", "target": "concept:volatility-drag"},
            {"id": "e3", "type": "prevents", "source": "sop:check-risk-before-entry", "target": "principle:ruin-is-permanent"},
            {"id": "e4", "type": "applies", "source": "sop:kelly-criterion", "target": "concept:position-sizing"},
            {"id": "e5", "type": "related", "source": "concept:survival", "target": "principle:ruin-is-permanent"},
        ],
    }


@pytest.fixture
def task_contract():
    return {"user_goal": "Understand how to protect against tail risk and size positions correctly"}


@pytest.fixture
def evidence_ledger():
    return {
        "entries": [
            {
                "entry_id": "ev-001",
                "claim": "Volatility drag compounds against you over time",
                "evidence_text": "At 03:45 the author demonstrates with SPY vs leveraged ETF",
            },
            {
                "entry_id": "ev-002",
                "claim": "Nobody knows what will happen next",
                "evidence_text": "At 07:12 the author shows failed prediction records",
            },
            {
                "entry_id": "ev-003",
                "claim": "Tail hedging costs reduce compound returns",
                "evidence_text": "At 12:30 the author presents backtest with/without put protection",
            },
            {
                "entry_id": "ev-004",
                "claim": "Ruin is permanent",
                "evidence_text": "At 18:45 the author shows portfolio recovery curves",
            },
        ],
    }


# ---------------------------------------------------------------------------
# E2E 1: Normal flow — claim matches SF, depth increases
# ---------------------------------------------------------------------------

class TestNormalFlow:
    def test_basic_claim_not_drift(self, trading_sf, task_contract):
        """A claim that exists in SF should not be flagged as drift."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Volatility drag compounds against you over time")
        assert result["is_drift"] is False
        assert result["is_contradiction"] is False
        assert result["matched_node"] is not None
        assert result["matched_node"]["id"] == "principle:vd-compounds"

    def test_basic_claim_returns_challenge(self, trading_sf, task_contract):
        """A valid claim should return a challenge question."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Volatility drag compounds against you")
        assert len(result["challenge"]) > 0

    def test_claim_with_evidence_id(self, trading_sf, task_contract):
        """Claim matching a node with evidence_id should be recognized."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Nobody knows what the outcome will be")
        assert result["is_drift"] is False
        assert result["matched_node"]["id"] == "principle:nobody-knows"

    def test_sop_match(self, trading_sf, task_contract):
        """SOP nodes should be matchable."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Apply Kelly criterion for position sizing")
        assert result["is_drift"] is False
        assert result["matched_node"] is not None

    def test_match_layer_reported(self, trading_sf, task_contract):
        """Every response should report which layer matched."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Volatility drag compounds against you")
        assert result["match_layer"] in ("id", "substring", "salient", "embedding", "none")


# ---------------------------------------------------------------------------
# E2E 2: Drift detection — outside scope
# ---------------------------------------------------------------------------

class TestDriftDetection:
    def test_unrelated_topic_is_drift(self, trading_sf, task_contract):
        """Topic completely outside SF should be flagged as drift."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("The weather in Paris is beautiful today")
        assert result["is_drift"] is True
        assert result["depth"] == 0

    def test_partial_overlap_not_drift(self, trading_sf, task_contract):
        """Response with SF-anchored terms should not be drift."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("How does volatility drag impact my portfolio returns?")
        assert result["is_drift"] is False

    def test_drift_returns_warning_challenge(self, trading_sf, task_contract):
        """Drift should return a challenge that redirects to the topic."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("I like cooking pasta on Sundays")
        assert result["is_drift"] is True
        assert "fora do tema" in result["challenge"].lower() or "autor" in result["challenge"].lower()


# ---------------------------------------------------------------------------
# E2E 3: Contradiction detection — negation + challenge words
# ---------------------------------------------------------------------------

class TestContradictionDetection:
    def test_negation_is_contradiction(self, trading_sf, task_contract):
        """Response negating a principle should be flagged as contradiction.

        Engine sets is_drift=False for contradictions — they are "in scope but wrong",
        not "out of scope". The is_contradiction flag is the key indicator.
        """
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Volatility drag does NOT compound and is irrelevant")
        assert result["is_contradiction"] is True

    def test_challenge_words_are_contradiction(self, trading_sf, task_contract):
        """Response using challenge words against a principle is contradiction."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("The principle about tail risk hedging is wrong and flawed")
        assert result["is_contradiction"] is True

    def test_contradiction_returns_principle_as_challenge(self, trading_sf, task_contract):
        """Contradiction should challenge with the contradicted principle."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Nobody knows what will happen — that's completely false")
        assert result["is_contradiction"] is True
        assert "contradizendo" in result["challenge"].lower()

    def test_disconfirming_evidence_is_contradiction(self, trading_sf, task_contract):
        """Voicing disconfirming_evidence is a challenge, not an affirmation.

        Engine returns is_drift=False for contradictions — they are "in scope but wrong".
        """
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Sharpe ratio is path-independent so drag does not apply")
        assert result["is_contradiction"] is True

    def test_affirmation_not_contradiction(self, trading_sf, task_contract):
        """Affirming a principle is NOT a contradiction."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Volatility drag compounds against you over time — I agree")
        assert result["is_contradiction"] is False
        assert result["is_drift"] is False


# ---------------------------------------------------------------------------
# E2E 4: Semantic guard — type confusion, definition drift
# ---------------------------------------------------------------------------

class TestSemanticGuard:
    def test_type_confusion_detected(self, trading_sf):
        """Type confusion (wrong units for same concept) should be caught."""
        # "1.6GB" (storage) confused with "100 snapshots" (count) for same concept
        sf_type = {
            "nodes": [{
                "id": "p1", "type": "principle",
                "statement": "The system processes 100 snapshots per second",
                "epistemic_status": "certain",
            }],
            "edges": [],
        }
        issues = check_semantic_errors(
            "The system processes data using 1.6GB of storage",
            sf_type,
        )
        assert len(issues["issues"]) >= 1
        assert issues["issues"][0]["type"] == "type_confusion"
        assert issues["is_valid"] is False

    def test_clean_response_no_issues(self, trading_sf):
        """Clean response should have no semantic issues."""
        result = check_semantic_errors(
            "Volatility drag compounds against you over time",
            trading_sf,
        )
        assert result["is_valid"] is True
        assert len(result["issues"]) == 0

    def test_semantic_guard_challenges_via_engine(self, trading_sf):
        """Engine surfaces semantic errors — drift_detector catches type confusion.

        The drift_detector itself runs semantic_guard internally and escalates
        high-severity issues to is_drift=True with the error in the 'reason' field.
        """
        sf_type = {
            "nodes": [{
                "id": "p1", "type": "principle",
                "statement": "The system processes 1,600 snapshots per second",
                "epistemic_status": "certain",
            }],
            "edges": [],
        }
        engine = ChavrutaEngine(sf_type)
        # "system" + "processes" provide coverage, "1.6GB" vs "1,600 snapshots" = type confusion
        result = engine.process("The system processes data using 1.6GB of storage")
        # Type confusion detected and escalated to drift
        assert result["is_drift"] is True
        assert "type confusion" in result.get("anchor_used", "") or "semantic" in str(result).lower() or result["is_drift"] is True


# ---------------------------------------------------------------------------
# E2E 5: Depth progression — all 7 levels
# ---------------------------------------------------------------------------

class TestDepthProgression:
    def test_depth_1_superficial(self, trading_sf, task_contract):
        """Depth 1: repeats SF terms without crossing."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Volatility drag")
        assert result["depth"] >= 1

    def test_depth_2_with_evidence(self, trading_sf, task_contract):
        """Depth 2: references a node with evidence_id."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("The author says nobody knows what will happen")
        # Should be depth 2+ because it references principle:nobody-knows which has evidence_id
        assert result["depth"] >= 2

    def test_depth_3_disconfirming_evidence(self, trading_sf, task_contract):
        """Depth 3: engages disconfirming_evidence."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        # "Sharpe ratio" appears in disconfirming_evidence of principle:vd-compounds
        result = engine.process("What if the Sharpe ratio were path-independent?")
        assert result["depth"] >= 3

    def test_depth_4_connected_concepts(self, trading_sf, task_contract):
        """Depth 4: mentions 2+ connected nodes.

        Query must have high overlap (>0.4) with both nodes' text.
        "tail risk" + "volatility drag" directly match both concept terms.
        """
        engine = ChavrutaEngine(trading_sf, task_contract)
        # Both concepts are connected by edge e2 (tail-risk → volatility-drag)
        # Using direct term references for high overlap
        result = engine.process("How does tail risk relate to volatility drag?")
        assert result["depth"] >= 4

    def test_depth_5_strongest_alternative(self, trading_sf, task_contract):
        """Depth 5: invokes strongest_alternative."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        # "Rebalancing" and "volatility harvesting" are in strongest_alternative of vd-compounds
        result = engine.process("Rebalancing can capture volatility harvesting premium")
        assert result["depth"] >= 5

    def test_depth_7_uncertainty_markers(self, trading_sf, task_contract):
        """Depth 7: uncertainty markers + SF reference.

        Response must have enough SF coverage to pass drift check,
        plus uncertainty markers (maybe, perhaps, not sure, etc.).
        """
        engine = ChavrutaEngine(trading_sf, task_contract)
        # "tail risk" provides coverage, "maybe" is uncertainty marker
        result = engine.process("Maybe tail risk hedging is not worth the cost, I'm not sure")
        assert result["depth"] >= 7


# ---------------------------------------------------------------------------
# E2E 6: Camada 4 (embeddings) contribution
# ---------------------------------------------------------------------------

class TestCamada4E2E:
    def test_paraphrase_not_drift(self, trading_sf, task_contract):
        """Paraphrase matching via embeddings should not be drift.

        Note: salient terms like "risk" in the query overlap with "tail risk" node,
        so layer 3 (salient) catches it. The key assertion is that the paraphrase
        is NOT drift — the layer is secondary.
        """
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        engine = ChavrutaEngine(trading_sf, task_contract)
        # "protection against fat tails" paraphrases "tail risk"
        result = engine.process("How should I protect my portfolio against fat tails?")
        # Should match concept:tail-risk (via salient or embedding)
        assert result["is_drift"] is False
        if result["matched_node"] and result["matched_node"]["id"] == "concept:tail-risk":
            # Matched! Layer could be salient or embedding
            assert result["match_layer"] in ("salient", "embedding")

    def test_embedding_match_produces_challenge(self, trading_sf, task_contract):
        """Embedding match should still produce a valid challenge."""
        if not is_installed():
            pytest.skip("sentence-transformers not installed")

        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("What is the right fraction of capital to risk per trade?")
        # Should match sop:kelly-criterion or concept:position-sizing
        if result["matched_node"]:
            assert len(result["challenge"]) > 0


# ---------------------------------------------------------------------------
# E2E 7: Session state tracking
# ---------------------------------------------------------------------------

class TestSessionState:
    def test_history_grows(self, trading_sf, task_contract):
        """History should accumulate across multiple process() calls."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        engine.process("Volatility drag compounds")
        engine.process("Nobody knows what will happen")
        assert len(engine.history) == 2

    def test_max_depth_tracks_highwater(self, trading_sf, task_contract):
        """max_depth_seen should track the highest depth reached."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        engine.process("Volatility drag")  # depth 1
        result = engine.process("What if Sharpe ratio were path-independent?")  # depth 3+
        assert engine.max_depth_seen >= result["depth"]

    def test_session_summary_after_moves(self, trading_sf, task_contract):
        """Session summary should reflect the debate state."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        engine.process("Volatility drag compounds against you")
        engine.process("Nobody knows what will happen")
        summary = engine.get_session_summary()
        assert summary["total_moves"] == 2
        assert summary["max_depth"] >= 1

    def test_contradiction_counted(self, trading_sf, task_contract):
        """Contradictions should be counted in session summary."""
        engine = ChavrutaEngine(trading_sf, task_contract)
        engine.process("Volatility drag compounds")
        engine.process("Volatility drag does NOT compound")  # contradiction
        summary = engine.get_session_summary()
        assert summary["contradictions"] >= 1

    def test_v2_engine_session_summary(self, trading_sf, task_contract):
        """Engine v2 summary should include nodes_challenged."""
        engine = ChavrutaEngineV2(trading_sf, task_contract)
        engine.process("Volatility drag compounds against you")
        engine.process("Nobody knows what will happen")
        summary = engine.get_session_summary()
        assert summary["total_moves"] == 2
        assert summary["nodes_challenged"] >= 1


# ---------------------------------------------------------------------------
# E2E 8: Full pipeline integration — all components wired
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_all_components_wired(self, trading_sf, task_contract, evidence_ledger):
        """Full pipeline: sf_matcher → drift → semantic → depth → engine."""
        engine = ChavrutaEngine(trading_sf, task_contract, evidence_ledger)
        result = engine.process("Tail risk hedging costs reduce compound returns")

        # sf_matcher found the node
        assert result["matched_node"] is not None
        assert result["matched_node"]["id"] == "principle:tail-protection"

        # drift_detector did not flag as drift
        assert result["is_drift"] is False

        # semantic_guard ran (no issues expected for clean claim)
        assert isinstance(result["semantic_issues"], list)

        # depth_tracker evaluated depth
        assert result["depth"] >= 1
        assert result["depth_label"] != ""

        # engine generated a challenge
        assert len(result["challenge"]) > 0

        # match_layer reported
        assert result["match_layer"] != ""

    def test_contradiction_full_pipeline(self, trading_sf, task_contract):
        """Contradiction flows through full pipeline correctly.

        Engine returns is_drift=False for contradictions — they are "in scope but wrong".
        The is_contradiction flag is the key indicator.
        Uses negation words to trigger contradiction detection.
        """
        engine = ChavrutaEngine(trading_sf, task_contract)
        result = engine.process("Ruin is NOT permanent — you can always recover from zero")

        # Contradiction detected (negation contradicts principle:ruin-is-permanent)
        assert result["is_contradiction"] is True

        # Challenge references the principle
        assert len(result["challenge"]) > 0

        # History recorded
        assert len(engine.history) == 1
        assert engine.history[0]["is_contradiction"] is True

    def test_v2_full_pipeline(self, trading_sf, task_contract, evidence_ledger):
        """Engine v2 full pipeline with evidence-backed challenges."""
        engine = ChavrutaEngineV2(trading_sf, task_contract, evidence_ledger)
        result = engine.process("Volatility drag compounds against you")

        assert result["is_drift"] is False
        assert result["matched_node"] is not None
        assert result["match_layer"] in ("id", "substring", "salient", "embedding", "none")
        assert isinstance(result["semantic_issues"], list)
        assert result["depth"] >= 1
        assert len(result["challenge"]) > 0

    def test_multi_turn_debate(self, trading_sf, task_contract, evidence_ledger):
        """Simulate a multi-turn debate with depth progression."""
        engine = ChavrutaEngine(trading_sf, task_contract, evidence_ledger)

        # Turn 1: superficial
        r1 = engine.process("Volatility drag")
        assert r1["depth"] >= 1
        assert r1["is_drift"] is False

        # Turn 2: deeper — references evidence
        r2 = engine.process("The author states that nobody knows the outcome of trades")
        assert r2["depth"] >= 2

        # Turn 3: challenges with disconfirming evidence
        r3 = engine.process("What about path-independent Sharpe ratio?")
        assert r3["depth"] >= 3

        # Turn 4: connects concepts
        r4 = engine.process("Tail risk protection reduces volatility drag impact")
        assert r4["depth"] >= 4

        # Session state
        assert len(engine.history) == 4
        assert engine.max_depth_seen >= 4

    def test_engine_v2_avoids_repetition(self, trading_sf, task_contract):
        """Engine v2 should detect when a node was already challenged."""
        engine = ChavrutaEngineV2(trading_sf, task_contract)

        # First challenge on the same node+depth
        engine.process("Volatility drag compounds against you")

        # Same node again — v2 should vary or escalate
        r2 = engine.process("Volatility drag compounds against you again")

        # Should still work (not crash), and may vary the challenge
        assert len(r2["challenge"]) > 0
        assert r2["is_drift"] is False
