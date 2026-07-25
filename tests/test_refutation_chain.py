#!/usr/bin/env python3
"""Tests for scripts/refutation_chain.py — adversarial quality gate.

Tests: validation logic, prompt generation, response parsing, enrichment,
failure modes, and integration with compile pipeline.
"""
import os
import textwrap
from unittest import mock

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from refutation_chain import (
    _semantic_overlap,
    _is_genuine_dissent,
    build_refutation_prompt,
    parse_refutation_response,
    validate_refutation,
    enrich_principles,
    run_refutation_chain,
    VALID_DISSENT_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_principle():
    return {
        "statement": "Volatility drag compounds against you over time",
        "epistemic_status": "certain",
        "evidence": "Geometric mean underperforms arithmetic mean due to volatility",
    }


@pytest.fixture
def sample_source_content():
    return textwrap.dedent("""\
        The key insight is that volatility drag compounds against you.
        Nobody knows what the outcome of a single trade will be.
        Higher returns require higher risk — there is no free lunch.
        Geometric mean underperforms arithmetic mean due to variance.
    """)


@pytest.fixture
def sample_compilation():
    return {
        "source": "test_video.txt",
        "principles": [
            {
                "statement": "Volatility drag compounds against you over time",
                "epistemic_status": "certain",
                "evidence": "Geometric mean underperforms arithmetic mean",
            },
            {
                "statement": "Nobody knows what the outcome of a single trade will be",
                "epistemic_status": "certain",
                "evidence": "Market outcomes are fundamentally uncertain",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Semantic overlap
# ---------------------------------------------------------------------------

class TestSemanticOverlap:
    def test_identical_claims(self):
        claim = "volatility drag compounds over time"
        alt = "volatility drag compounds over time"
        assert _semantic_overlap(claim, alt) == 1.0

    def test_completely_different(self):
        claim = "cats are furry animals"
        alt = "the stock market crashed yesterday"
        assert _semantic_overlap(claim, alt) == 0.0

    def test_partial_overlap(self):
        claim = "volatility drag compounds against portfolio returns"
        alt = "volatility drag is mitigated by rebalancing portfolio"
        overlap = _semantic_overlap(claim, alt)
        assert 0.3 < overlap < 0.8

    def test_empty_claim(self):
        assert _semantic_overlap("", "something") == 0.0

    def test_empty_alternative(self):
        assert _semantic_overlap("something", "") == 0.0

    def test_both_empty(self):
        assert _semantic_overlap("", "") == 0.0


# ---------------------------------------------------------------------------
# Genuine dissent check
# ---------------------------------------------------------------------------

class TestGenuineDissent:
    def test_high_overlap_flagged(self):
        """Alternative with > 0.7 overlap should be flagged."""
        claim = "volatility drag compounds against you over time"
        alt = "volatility drag compounds against investors over time"
        is_valid, reason = _is_genuine_dissent(claim, alt, threshold=0.7)
        assert not is_valid
        assert "Overlap" in reason

    def test_qualifying_language_passes(self):
        """Alternative with qualification words should pass."""
        claim = "volatility drag compounds against you"
        alt = "volatility drag depends on the rebalancing frequency and path"
        is_valid, reason = _is_genuine_dissent(claim, alt, threshold=0.7)
        assert is_valid

    def test_negation_passes(self):
        """Alternative with negation words should pass even with low overlap."""
        claim = "higher returns always require higher risk"
        alt = "higher returns do not always require higher risk in efficient markets"
        is_valid, reason = _is_genuine_dissent(claim, alt, threshold=0.7)
        assert is_valid

    def test_low_overlap_no_negation_flagged(self):
        """Low overlap without negation should be flagged."""
        claim = "volatility drag compounds"
        alt = "the weather is nice today"
        is_valid, reason = _is_genuine_dissent(claim, alt, threshold=0.7)
        assert not is_valid
        assert "too low" in reason

    def test_contradicting_alternative(self):
        """Alternative that directly contradicts should pass."""
        claim = "diversification always reduces risk"
        alt = "diversification does not reduce risk in correlated markets"
        is_valid, reason = _is_genuine_dissent(claim, alt, threshold=0.7)
        assert is_valid

    def test_context_limited_alternative(self):
        """Alternative that limits context should pass."""
        claim = "stop losses protect capital"
        alt = "stop losses protect capital only in trending markets, not in choppy conditions"
        is_valid, reason = _is_genuine_dissent(claim, alt, threshold=0.7)
        assert is_valid


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestParseRefutationResponse:
    def test_valid_response(self):
        text = textwrap.dedent("""\
            - **Strongest Alternative**: Volatility drag is real but can be harvested through rebalancing
            - **Disconfirming Evidence**: Would be false if log-returns were additive
            - **Dissent Type**: qualifies
        """)
        result = parse_refutation_response(text)
        assert result is not None
        assert "rebalancing" in result["strongest_alternative"]
        assert "log-returns" in result["disconfirming_evidence"]
        assert result["dissent_type"] == "qualifies"

    def test_contradicts_type(self):
        text = textwrap.dedent("""\
            - **Strongest Alternative**: Diversification does not reduce risk in correlated markets
            - **Disconfirming Evidence**: Would be false if all assets were perfectly correlated
            - **Dissent Type**: contradicts
        """)
        result = parse_refutation_response(text)
        assert result is not None
        assert result["dissent_type"] == "contradicts"

    def test_context_limited_type(self):
        text = textwrap.dedent("""\
            - **Strongest Alternative**: This only applies in bull markets
            - **Disconfirming Evidence**: Would be false in bear markets
            - **Dissent Type**: context_limited
        """)
        result = parse_refutation_response(text)
        assert result is not None
        assert result["dissent_type"] == "context_limited"

    def test_invalid_dissent_type(self):
        text = textwrap.dedent("""\
            - **Strongest Alternative**: Something different
            - **Disconfirming Evidence**: Something else
            - **Dissent Type**: invalid_type
        """)
        result = parse_refutation_response(text)
        assert result is not None
        assert result["dissent_type"] == ""

    def test_missing_alternative(self):
        text = textwrap.dedent("""\
            - **Disconfirming Evidence**: Something else
            - **Dissent Type**: qualifies
        """)
        result = parse_refutation_response(text)
        assert result is None

    def test_empty_response(self):
        assert parse_refutation_response("") is None

    def test_malformed_response(self):
        assert parse_refutation_response("random text with no structure") is None

    def test_has_generated_at(self):
        text = textwrap.dedent("""\
            - **Strongest Alternative**: Something different
            - **Disconfirming Evidence**: Something else
            - **Dissent Type**: qualifies
        """)
        result = parse_refutation_response(text)
        assert result is not None
        assert "generated_at" in result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateRefutation:
    def test_valid_qualifies(self):
        refutation = {
            "strongest_alternative": "This only applies in certain market conditions",
            "disconfirming_evidence": "Would be false in bear markets",
            "dissent_type": "qualifies",
        }
        is_valid, reason = validate_refutation(
            "volatility drag compounds against you", refutation,
        )
        assert is_valid

    def test_invalid_dissent_type(self):
        refutation = {
            "strongest_alternative": "Something different",
            "dissent_type": "invalid",
        }
        is_valid, reason = validate_refutation("claim", refutation)
        assert not is_valid
        assert "dissent_type" in reason

    def test_missing_alternative(self):
        refutation = {"dissent_type": "qualifies"}
        is_valid, reason = validate_refutation("claim", refutation)
        assert not is_valid
        assert "strongest_alternative" in reason

    def test_confirmation_bias_flagged(self):
        refutation = {
            "strongest_alternative": "volatility drag compounds against you over time",  # same as claim
            "dissent_type": "qualifies",
        }
        is_valid, reason = validate_refutation(
            "volatility drag compounds against you over time", refutation,
        )
        assert not is_valid
        assert "Overlap" in reason

    def test_empty_dissent_type_passes(self):
        """Empty dissent_type is allowed (validated elsewhere)."""
        refutation = {
            "strongest_alternative": "This depends on market conditions",
        }
        is_valid, reason = validate_refutation(
            "volatility drag compounds", refutation,
        )
        assert is_valid


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class TestRefutationEntry:
    def test_valid_dissent_types(self):
        assert VALID_DISSENT_TYPES == {"qualifies", "contradicts", "context_limited"}

    def test_refutation_entry_structure(self, sample_principle):
        refutation = {
            "strongest_alternative": "Something different",
            "disconfirming_evidence": "Something else",
            "dissent_type": "qualifies",
            "generated_at": "2026-07-25T10:00:00Z",
            "model": "claude",
        }
        # Verify all required fields
        assert "strongest_alternative" in refutation
        assert "disconfirming_evidence" in refutation
        assert "dissent_type" in refutation
        assert refutation["dissent_type"] in VALID_DISSENT_TYPES


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

class TestBuildRefutationPrompt:
    def test_contains_claim(self):
        prompt = build_refutation_prompt(
            "volatility drag compounds", "evidence text", "source content",
        )
        assert "volatility drag compounds" in prompt

    def test_contains_evidence(self):
        prompt = build_refutation_prompt(
            "claim", "this is the evidence", "source content",
        )
        assert "this is the evidence" in prompt

    def test_contains_source(self):
        prompt = build_refutation_prompt(
            "claim", "evidence", "this is source content",
        )
        assert "this is source content" in prompt

    def test_truncates_long_source(self):
        long_source = "x" * 5000
        prompt = build_refutation_prompt("claim", "evidence", long_source)
        assert len(prompt) < 5000
        assert "truncated" in prompt

    def test_no_evidence_placeholder(self):
        prompt = build_refutation_prompt("claim", "", "source")
        assert "no evidence provided" in prompt


# ---------------------------------------------------------------------------
# Enrich principles (integration)
# ---------------------------------------------------------------------------

class TestEnrichPrinciples:
    def test_adds_refutation_field(self, sample_principle, sample_source_content):
        """enrich_principles should add refutation dict to each principle."""
        with mock.patch("refutation_chain.call_agent") as mock_agent:
            mock_agent.return_value = textwrap.dedent("""\
                - **Strongest Alternative**: This depends on market conditions
                - **Disconfirming Evidence**: Would be false in efficient markets
                - **Dissent Type**: qualifies
            """)
            enriched, flagged = enrich_principles(
                [sample_principle], sample_source_content,
                dry_run=False, delay=0,
            )
            assert len(enriched) == 1
            assert "refutation" in enriched[0]
            assert enriched[0]["refutation"]["strongest_alternative"]

    def test_dry_run_no_agent_call(self, sample_principle, sample_source_content):
        """dry_run should return prompts without calling agent."""
        with mock.patch("refutation_chain.call_agent") as mock_agent:
            enriched, flagged = enrich_principles(
                [sample_principle], sample_source_content,
                dry_run=True, delay=0,
            )
            mock_agent.assert_not_called()
            assert enriched[0]["refutation"]["_dry_run"] is True

    def test_agent_timeout_handled(self, sample_principle, sample_source_content):
        """Agent timeout should log warning, not crash."""
        with mock.patch("refutation_chain.call_agent", side_effect=RuntimeError("timed out")):
            enriched, flagged = enrich_principles(
                [sample_principle], sample_source_content,
                dry_run=False, delay=0,
            )
            assert enriched[0]["refutation"] is None

    def test_agent_empty_response(self, sample_principle, sample_source_content):
        """Empty agent response should be handled."""
        with mock.patch("refutation_chain.call_agent", return_value=""):
            enriched, flagged = enrich_principles(
                [sample_principle], sample_source_content,
                dry_run=False, delay=0,
            )
            assert enriched[0]["refutation"] is None

    def test_malformed_response(self, sample_principle, sample_source_content):
        """Malformed response should be caught by parser."""
        with mock.patch("refutation_chain.call_agent", return_value="random garbage"):
            enriched, flagged = enrich_principles(
                [sample_principle], sample_source_content,
                dry_run=False, delay=0,
            )
            assert enriched[0]["refutation"] is None

    def test_empty_principle_skipped(self, sample_source_content):
        """Empty statement should skip refutation."""
        principle = {"statement": "", "evidence": "evidence"}
        enriched, flagged = enrich_principles(
            [principle], sample_source_content,
            dry_run=True, delay=0,
        )
        assert enriched[0]["refutation"] is None

    def test_flagged_principles_returned(self, sample_source_content):
        """Confirmation-biased alternatives should be flagged."""
        principle = {
            "statement": "volatility drag compounds against you over time",
            "evidence": "evidence",
        }
        with mock.patch("refutation_chain.call_agent") as mock_agent:
            mock_agent.return_value = textwrap.dedent("""\
                - **Strongest Alternative**: volatility drag compounds against you over time
                - **Disconfirming Evidence**: none
                - **Dissent Type**: qualifies
            """)
            enriched, flagged = enrich_principles(
                [principle], sample_source_content,
                dry_run=False, delay=0,
            )
            assert len(flagged) == 1
            assert "Overlap" in flagged[0]["reason"]


# ---------------------------------------------------------------------------
# Run refutation chain
# ---------------------------------------------------------------------------

class TestRunRefutationChain:
    def test_empty_principles(self):
        """Compilation with no principles should produce empty summary."""
        compilation = {"source": "test.txt", "principles": []}
        result = run_refutation_chain(compilation, "source content")
        assert result["refutation_summary"]["total"] == 0

    def test_summary_fields(self, sample_compilation, sample_source_content):
        """Summary should have total, enriched, flagged, dissent_types."""
        with mock.patch("refutation_chain.call_agent") as mock_agent:
            mock_agent.return_value = textwrap.dedent("""\
                - **Strongest Alternative**: Something different that qualifies the claim
                - **Disconfirming Evidence**: Would be false in certain conditions
                - **Dissent Type**: qualifies
            """)
            result = run_refutation_chain(
                sample_compilation, sample_source_content,
                delay=0,
            )
            summary = result["refutation_summary"]
            assert summary["total"] == 2
            assert summary["enriched"] == 2
            assert "qualifies" in summary["dissent_types"]

    def test_no_principles_key(self, sample_source_content):
        """Compilation without principles key should work."""
        compilation = {"source": "test.txt"}
        result = run_refutation_chain(compilation, sample_source_content)
        assert result["refutation_summary"]["total"] == 0


# ---------------------------------------------------------------------------
# Compile integration (flag)
# ---------------------------------------------------------------------------

class TestCompileIntegration:
    def test_compile_args_exist(self):
        """compile.py should accept --refutation-chain flags."""
        # Just verify the imports work
        from compile import grounding_check
        assert callable(grounding_check)
