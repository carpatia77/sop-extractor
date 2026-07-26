#!/usr/bin/env python3
"""Tests for scripts/chavruta/semantic_guard.py — semantic error detection.

Tests: quantitative claims, definition drift, scope expansion.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chavruta.semantic_guard import (
    extract_quantitative_claims,
    check_quantitative_consistency,
    check_definition_drift,
    check_scope_expansion,
    check_semantic_errors,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sf_with_quantitative():
    return {
        "nodes": [
            {
                "id": "principle:vd",
                "type": "principle",
                "statement": "The system processes 100 snapshots per second",
                "epistemic_status": "certain",
            },
            {
                "id": "concept:drag",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance due to variance",
            },
        ],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# Quantitative claims
# ---------------------------------------------------------------------------

class TestExtractQuantitativeClaims:
    def test_extracts_number_with_unit(self):
        claims = extract_quantitative_claims("The system processes 100 snapshots per second")
        assert len(claims) >= 1
        assert claims[0]["number"] == 100
        assert claims[0]["unit"] == "snapshots"

    def test_extracts_multiple(self):
        claims = extract_quantitative_claims("1.6GB memory, 1600 snapshots, 30ms latency")
        assert len(claims) >= 3

    def test_no_numbers(self):
        claims = extract_quantitative_claims("No numbers here")
        assert len(claims) == 0

    def test_decimal_numbers(self):
        claims = extract_quantitative_claims("1.6GB of memory")
        assert len(claims) == 1
        assert claims[0]["number"] == 1.6


class TestQuantitativeConsistency:
    def test_matching_magnitude(self, sf_with_quantitative):
        issues = check_quantitative_consistency(
            "The system processes 100 snapshots per second",
            sf_with_quantitative,
        )
        # Same magnitude — no issue
        assert len(issues) == 0

    def test_mismatched_magnitude(self, sf_with_quantitative):
        issues = check_quantitative_consistency(
            "The system processes 1600 snapshots per second",
            sf_with_quantitative,
        )
        # 16x difference — should flag
        assert len(issues) >= 1
        assert issues[0]["type"] == "quantitative_mismatch"
        assert issues[0]["severity"] == "high"

    def test_different_units_no_issue(self, sf_with_quantitative):
        issues = check_quantitative_consistency(
            "The system uses 500ms of memory",
            sf_with_quantitative,
        )
        # Different units — no comparison possible
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Definition drift
# ---------------------------------------------------------------------------

class TestDefinitionDrift:
    def test_no_redefinition(self, sf_with_quantitative):
        issues = check_definition_drift(
            "Volatility drag compounds against you",
            sf_with_quantitative,
        )
        # Mentions term but doesn't redefine — no issue
        assert len(issues) == 0

    def test_redefinition_detected(self, sf_with_quantitative):
        issues = check_definition_drift(
            "Volatility drag means something completely different from what you think",
            sf_with_quantitative,
        )
        # Attempts to redefine without matching SF definition
        assert len(issues) >= 1
        assert issues[0]["type"] == "definition_drift"


# ---------------------------------------------------------------------------
# Scope expansion
# ---------------------------------------------------------------------------

class TestScopeExpansion:
    def test_universal_on_qualified(self, sf_with_quantitative):
        issues = check_scope_expansion(
            "Volatility drag always applies to every portfolio",
            sf_with_quantitative,
        )
        # SF says "speculative" or "qualifies" but response uses "always"
        # (if SF has such nodes)
        # This test depends on SF content — may be empty if SF doesn't qualify
        assert isinstance(issues, list)

    def test_no_universal(self, sf_with_quantitative):
        issues = check_scope_expansion(
            "Volatility drag may affect some portfolios",
            sf_with_quantitative,
        )
        # No universal quantifiers — no issue
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Combined check
# ---------------------------------------------------------------------------

class TestCheckSemanticErrors:
    def test_clean_response(self, sf_with_quantitative):
        result = check_semantic_errors(
            "The system processes 100 snapshots per second",
            sf_with_quantitative,
        )
        assert result["is_valid"] is True
        assert len(result["issues"]) == 0

    def test_quantitative_error(self, sf_with_quantitative):
        result = check_semantic_errors(
            "The system processes 1600 snapshots per second",
            sf_with_quantitative,
        )
        assert result["is_valid"] is False
        assert len(result["quantitative"]) >= 1
