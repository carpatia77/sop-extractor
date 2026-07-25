#!/usr/bin/env python3
"""Tests for scripts/cross_analysis.py — Cross-Analysis consolidator."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from cross_analysis import (
    load_compilations,
    consolidate,
    detect_themes,
    extract_gold,
    suggest_links,
    generate_report,
    run_cross_analysis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def compilation_a():
    return {
        "source": "video_a.txt",
        "compiled_at": "2026-07-24T00:00:00Z",
        "concepts": [
            {"term": "Volatility Drag", "definition": "Penalty on compound growth", "used_in": "SOP A"},
            {"term": "Sharpe Ratio", "definition": "Risk-adjusted return", "used_in": ""},
            {"term": "Convexity", "definition": "Curvature in growth", "used_in": "SOP A"},
        ],
        "principles": [
            {"statement": "Higher returns require higher risk", "epistemic_status": "certain", "evidence": "quote"},
        ],
        "sops": [{"name": "SOP A", "steps": ["Step 1"], "when_to_use": "Always"}],
        "references": ["CAPM"],
    }


@pytest.fixture
def compilation_b():
    return {
        "source": "video_b.txt",
        "compiled_at": "2026-07-24T00:00:00Z",
        "concepts": [
            {"term": "Volatility Drag", "definition": "Penalty on compound growth", "used_in": "SOP B"},
            {"term": "Hedge Sleeve", "definition": "Portfolio insurance layer", "used_in": "SOP B"},
            {"term": "Convexity", "definition": "Curvature in growth", "used_in": "SOP B"},
        ],
        "principles": [
            {"statement": "Higher returns require higher risk", "epistemic_status": "certain", "evidence": "quote"},
            {"statement": "Hedging reduces volatility drag", "epistemic_status": "probable", "evidence": "evidence"},
        ],
        "sops": [{"name": "SOP B", "steps": ["Step 1"], "when_to_use": "When hedging"}],
        "references": ["Black-Scholes"],
    }


@pytest.fixture
def compilation_c():
    """Unique concepts only in this video."""
    return {
        "source": "video_c.txt",
        "compiled_at": "2026-07-24T00:00:00Z",
        "concepts": [
            {"term": "Lottery Ticket Effect", "definition": "Psychological trap", "used_in": ""},
            {"term": "Regime Change", "definition": "Market dynamics shift", "used_in": ""},
        ],
        "principles": [],
        "sops": [],
        "references": [],
    }


@pytest.fixture
def compilations(compilation_a, compilation_b, compilation_c):
    return [compilation_a, compilation_b, compilation_c]


@pytest.fixture
def tmp_compilations(tmp_path, compilation_a, compilation_b, compilation_c):
    """Write compilations to temp directory for load_compilations test."""
    comp_dir = tmp_path / "compilation"
    comp_dir.mkdir()
    for i, comp in enumerate([compilation_a, compilation_b, compilation_c]):
        with open(comp_dir / f"video_{i}.json", "w") as f:
            json.dump(comp, f)
    # Add run.json that should be excluded
    with open(comp_dir / "run.json", "w") as f:
        json.dump({"total_videos": 3}, f)
    return tmp_path


# ---------------------------------------------------------------------------
# Load compilations
# ---------------------------------------------------------------------------

class TestLoadCompilations:
    def test_loads_all(self, tmp_compilations):
        comps = load_compilations(tmp_compilations)
        assert len(comps) == 3

    def test_excludes_run_json(self, tmp_compilations):
        comps = load_compilations(tmp_compilations)
        for c in comps:
            assert "total_videos" not in c or "concepts" in c

    def test_empty_dir(self, tmp_path):
        comps = load_compilations(tmp_path)
        assert comps == []


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------

class TestConsolidate:
    def test_node_count(self, compilations):
        result = consolidate(compilations)
        # 3 unique concepts (Volatility Drag, Sharpe Ratio, Convexity, Hedge Sleeve, Lottery Ticket Effect, Regime Change) + 2 principles
        assert result["metadata"]["n_concepts"] == 6
        assert result["metadata"]["n_principles"] == 2

    def test_frequency_tracking(self, compilations):
        result = consolidate(compilations)
        concepts = {n["term"]: n for n in result["nodes"] if n["type"] == "concept"}
        # Volatility Drag appears in 2 videos
        assert concepts["Volatility Drag"]["frequency"] == 2
        # Sharpe Ratio appears in 1
        assert concepts["Sharpe Ratio"]["frequency"] == 1

    def test_source_files_tracking(self, compilations):
        result = consolidate(compilations)
        concepts = {n["term"]: n for n in result["nodes"] if n["type"] == "concept"}
        vd = concepts["Volatility Drag"]
        assert "video_a.txt" in vd["source_files"]
        assert "video_b.txt" in vd["source_files"]
        assert "video_c.txt" not in vd["source_files"]

    def test_co_occurrence_edges(self, compilations):
        result = consolidate(compilations)
        co_edges = [e for e in result["edges"] if e["type"] == "co_occurs"]
        # Volatility Drag + Convexity co-occur in videos A and B
        vd_convex = [e for e in co_edges
                     if "volatility-drag" in e["source"] and "convexity" in e["target"]
                     or "convexity" in e["source"] and "volatility-drag" in e["target"]]
        assert len(vd_convex) >= 1

    def test_total_sources(self, compilations):
        result = consolidate(compilations)
        assert result["total_sources"] == 3

    def test_source_files_list(self, compilations):
        result = consolidate(compilations)
        assert len(result["source_files"]) == 3


# ---------------------------------------------------------------------------
# Theme detection
# ---------------------------------------------------------------------------

class TestDetectThemes:
    def test_finds_theme(self, compilations):
        consolidated = consolidate(compilations)
        themes = detect_themes(consolidated, min_cooccurrence=2)
        # Volatility Drag + Convexity co-occur in 2+ videos
        assert len(themes) >= 1

    def test_theme_has_members(self, compilations):
        consolidated = consolidate(compilations)
        themes = detect_themes(consolidated, min_cooccurrence=2)
        for t in themes:
            assert len(t["members"]) >= 2
            assert t["total_frequency"] > 0

    def test_theme_sorted_by_frequency(self, compilations):
        consolidated = consolidate(compilations)
        themes = detect_themes(consolidated, min_cooccurrence=2)
        freqs = [t["total_frequency"] for t in themes]
        assert freqs == sorted(freqs, reverse=True)


# ---------------------------------------------------------------------------
# Gold extraction
# ---------------------------------------------------------------------------

class TestExtractGold:
    def test_unique_concepts_are_gold(self, compilations):
        consolidated = consolidate(compilations)
        gold = extract_gold(consolidated, max_videos=1)
        gold_terms = {g["term"] for g in gold}
        # Sharpe Ratio, Hedge Sleeve, Lottery Ticket Effect, Regime Change are unique
        assert "Sharpe Ratio" in gold_terms or "Lottery Ticket Effect" in gold_terms

    def test_rare_concepts_high_rarity(self, compilations):
        consolidated = consolidate(compilations)
        gold = extract_gold(consolidated, max_videos=1)
        for g in gold:
            assert g["rarity_score"] > 0

    def test_sorted_by_rarity(self, compilations):
        consolidated = consolidate(compilations)
        gold = extract_gold(consolidated, max_videos=2)
        rarities = [g["rarity_score"] for g in gold]
        assert rarities == sorted(rarities, reverse=True)


# ---------------------------------------------------------------------------
# Link suggestion
# ---------------------------------------------------------------------------

class TestSuggestLinks:
    def test_suggests_links(self, compilations):
        consolidated = consolidate(compilations)
        links = suggest_links(consolidated, min_cooccurrence=2)
        # May or may not have links depending on edge structure
        assert isinstance(links, list)

    def test_link_has_required_fields(self, compilations):
        consolidated = consolidate(compilations)
        links = suggest_links(consolidated, min_cooccurrence=2)
        for l in links:
            assert "source" in l
            assert "target" in l
            assert "co_occurrence_count" in l

    @staticmethod
    def _comp(path, terms, used_in_map):
        """Build a compilation where each term is used_in a named SOP."""
        concepts = [
            {"term": t, "definition": f"def {t}", "used_in": used_in_map.get(t, "")}
            for t in terms
        ]
        sops = sorted({s for s in used_in_map.values() if s})
        return {
            "source_path": path,
            "concepts": concepts,
            "principles": [],
            "sops": [{"name": s, "when_to_use": "x"} for s in sops],
            "references": [],
        }

    def test_shared_target_pair_is_filtered(self):
        """Regression: two concepts that both point to the SAME SOP are
        'already related' and must NOT be suggested as a missing link —
        even though they co-occur across every video. This filter regressed
        twice (always-empty, then filter-never-fires); lock it here."""
        comps = [
            self._comp(f"v{i}.txt", ["Alpha", "Beta"],
                       {"Alpha": "Build Portfolio", "Beta": "Build Portfolio"})
            for i in range(3)
        ]
        links = suggest_links(consolidate(comps), min_cooccurrence=2)
        pairs = {(l["source_term"], l["target_term"]) for l in links}
        assert ("Alpha", "Beta") not in pairs
        assert ("Beta", "Alpha") not in pairs

    def test_unshared_target_pair_is_suggested(self):
        """Two concepts that co-occur but point to DIFFERENT SOPs (no shared
        target) are not yet explicitly related and SHOULD be suggested."""
        comps = [
            self._comp(f"v{i}.txt", ["Alpha", "Beta"],
                       {"Alpha": "SOP-A", "Beta": "SOP-B"})
            for i in range(3)
        ]
        links = suggest_links(consolidate(comps), min_cooccurrence=2)
        pairs = {tuple(sorted([l["source_term"], l["target_term"]])) for l in links}
        assert ("Alpha", "Beta") in pairs


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_has_sections(self, compilations):
        consolidated = consolidate(compilations)
        themes = detect_themes(consolidated)
        gold = extract_gold(consolidated)
        links = suggest_links(consolidated)
        report = generate_report(consolidated, themes, gold, links)
        assert "## Corpus Overview" in report
        assert "## Most Frequent Concepts" in report
        assert "## Themes" in report

    def test_report_has_data(self, compilations):
        consolidated = consolidate(compilations)
        report = generate_report(consolidated, [], [], [])
        assert "3 videos" in report


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_run(self, compilations):
        consolidated = consolidate(compilations)
        themes = detect_themes(consolidated)
        gold = extract_gold(consolidated)
        links = suggest_links(consolidated)
        report = generate_report(consolidated, themes, gold, links)

        assert consolidated["metadata"]["total_nodes"] > 0
        assert isinstance(themes, list)
        assert isinstance(gold, list)
        assert isinstance(links, list)
        assert len(report) > 100

    def test_run_cross_analysis(self, tmp_compilations, tmp_path):
        output_dir = tmp_path / "output"
        result = run_cross_analysis(tmp_compilations, output_dir)
        assert result["consolidated"]["metadata"]["total_nodes"] > 0
        assert (output_dir / "cross_analysis.json").exists()
        assert (output_dir / "cross_analysis.md").exists()

    def test_with_real_data(self):
        """Test with real compilation files if available."""
        comp_dir = os.path.join(
            os.path.dirname(__file__), "..",
            "output", "quantguild_transcripts",
        )
        if not os.path.isdir(comp_dir):
            pytest.skip("Real data not available")

        comps = load_compilations(comp_dir)
        if len(comps) < 3:
            pytest.skip("Not enough compilations")

        consolidated = consolidate(comps)
        themes = detect_themes(consolidated)
        gold = extract_gold(consolidated)
        report = generate_report(consolidated, themes, gold, [])

        assert consolidated["metadata"]["total_nodes"] > 0
        assert consolidated["total_sources"] == len(comps)
        print(f"\n{report[:500]}")
