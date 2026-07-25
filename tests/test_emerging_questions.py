#!/usr/bin/env python3
"""Tests for scripts/emerging_questions.py — gap, tension, limit detection.

Tests: each detector, main generator, file I/O, edge cases.
"""
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from emerging_questions import (
    detect_undefined_concepts,
    detect_principles_without_evidence,
    detect_sops_without_conditions,
    detect_orphan_concepts,
    detect_refutation_tensions,
    detect_epistemic_uncertainty,
    detect_sparse_connections,
    generate_emerging_questions,
    save_emerging_questions,
    load_emerging_questions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_sf():
    return {
        "nodes": [
            {
                "id": "concept:vd",
                "type": "concept",
                "term": "Volatility Drag",
                "definition": "Geometric underperformance due to variance",
            },
            {
                "id": "concept:short",
                "type": "concept",
                "term": "VRP",
                "definition": "",  # undefined
            },
            {
                "id": "principle:vd",
                "type": "principle",
                "statement": "Volatility drag compounds against you",
                "epistemic_status": "certain",
                "evidence": "Author states at 12:34 that drag compounds",
                "strongest_alternative": "Rebalancing can mitigate drag",
                "dissent_type": "qualifies",
            },
            {
                "id": "principle:no-ev",
                "type": "principle",
                "statement": "Some principle without evidence",
                "epistemic_status": "speculative",
                "evidence": "",  # no evidence
            },
            {
                "id": "sop:bp",
                "type": "sop",
                "name": "Build Portfolio",
                "when_to_use": "",  # no conditions
            },
            {
                "id": "sop:hp",
                "type": "sop",
                "name": "Hedge Portfolio",
                "when_to_use": "When volatility is high",
            },
        ],
        "edges": [
            {"id": "edge:0001", "type": "used_in", "source": "concept:vd", "target": "sop:bp"},
            {"id": "edge:0002", "type": "references", "source": "principle:vd", "target": "concept:vd"},
        ],
    }


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

class TestGapDetection:
    def test_undefined_concepts(self, sample_sf):
        gaps = detect_undefined_concepts(sample_sf)
        assert len(gaps) == 1
        assert gaps[0]["term"] == "VRP"

    def test_principles_without_evidence(self, sample_sf):
        gaps = detect_principles_without_evidence(sample_sf)
        assert len(gaps) == 1
        assert "no-ev" in gaps[0]["node_id"]

    def test_sops_without_conditions(self, sample_sf):
        gaps = detect_sops_without_conditions(sample_sf)
        assert len(gaps) == 1
        assert gaps[0]["name"] == "Build Portfolio"

    def test_orphan_concepts(self, sample_sf):
        gaps = detect_orphan_concepts(sample_sf)
        # concept:vd is connected (edge:0001, edge:0002)
        # concept:short is NOT connected
        assert len(gaps) == 1
        assert gaps[0]["term"] == "VRP"


# ---------------------------------------------------------------------------
# Tension detection
# ---------------------------------------------------------------------------

class TestTensionDetection:
    def test_refutation_tensions(self, sample_sf):
        tensions = detect_refutation_tensions(sample_sf)
        assert len(tensions) == 1
        assert tensions[0]["dissent_type"] == "qualifies"

    def test_epistemic_uncertainty(self, sample_sf):
        uncertainties = detect_epistemic_uncertainty(sample_sf)
        assert len(uncertainties) == 1
        assert uncertainties[0]["type"] == "epistemic_uncertainty"


# ---------------------------------------------------------------------------
# Limit detection
# ---------------------------------------------------------------------------

class TestLimitDetection:
    def test_sparse_connections(self, sample_sf):
        limits = detect_sparse_connections(sample_sf)
        # concept:short and sop:hp have 0 connections each
        assert len(limits) >= 1


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

class TestGenerator:
    def test_generates_all_types(self, sample_sf):
        result = generate_emerging_questions(sample_sf)
        assert result["summary"]["total"] > 0
        assert "by_type" in result["summary"]
        assert "by_severity" in result["summary"]

    def test_selective_detection(self, sample_sf):
        result = generate_emerging_questions(
            sample_sf, include_gaps=False, include_tensions=False, include_limits=False,
        )
        assert result["summary"]["total"] == 0

    def test_empty_sf(self):
        result = generate_emerging_questions({"nodes": [], "edges": []})
        assert result["summary"]["total"] == 0


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

class TestFileIO:
    def test_save_and_load(self, sample_sf, tmp_path):
        result = generate_emerging_questions(sample_sf)
        paths = save_emerging_questions(result, tmp_path / "eq")
        assert os.path.exists(paths["json"])
        assert os.path.exists(paths["markdown"])

        loaded = load_emerging_questions(tmp_path / "eq")
        assert loaded is not None
        assert loaded["summary"]["total"] == result["summary"]["total"]

    def test_load_nonexistent(self, tmp_path):
        assert load_emerging_questions(tmp_path / "nonexistent") is None

    def test_markdown_content(self, sample_sf, tmp_path):
        result = generate_emerging_questions(sample_sf)
        save_emerging_questions(result, tmp_path / "eq")
        md = (tmp_path / "eq" / "emerging_questions.md").read_text()
        assert "Emerging Questions" in md
        assert "High" in md or "Medium" in md or "Low" in md
