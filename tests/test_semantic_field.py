#!/usr/bin/env python3
"""Tests for scripts/semantic_field.py — Semantic Field builder, validation, exports."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import importlib.util
HAS_NETWORKX = importlib.util.find_spec("networkx") is not None

from semantic_field import (
    build_semantic_field,
    validate_semantic_field,
    export_graphml,
    export_jsonld,
    export_markdown,
    concept_id,
    principle_id,
    sop_id,
    reference_id,
    slugify,
    _coalesce_definition,
    _split_used_in,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_compilation():
    return {
        "source": "test_video.txt",
        "source_sha256": "abc123",
        "compiled_at": "2026-07-24T23:20:00Z",
        "sops": [
            {"name": "Portfolio Check", "steps": ["Step 1"], "when_to_use": "Always"},
        ],
        "principles": [
            {"statement": "Volatility drag compounds against you", "epistemic_status": "certain", "evidence": "according to CAPM, risk is compensated"},
            {"statement": "Higher returns require higher risk", "epistemic_status": "certain", "evidence": "Black-Scholes shows this relationship"},
        ],
        "concepts": [
            {"term": "Volatility Drag", "definition": "The penalty on compound growth", "used_in": "Portfolio Check"},
            {"term": "Sharpe Ratio", "description": "Risk-adjusted return metric", "used_in": ""},
        ],
        "references": ["CAPM", "Black-Scholes"],
    }


@pytest.fixture
def empty_compilation():
    return {
        "source": "empty.txt",
        "compiled_at": "2026-07-24T00:00:00Z",
        "sops": [],
        "principles": [],
        "concepts": [],
        "references": [],
    }


# ---------------------------------------------------------------------------
# Slugify + ID generation
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("Sharpe Ratio (risk-adjusted)") == "sharpe-ratio-risk-adjusted"

    def test_accents(self):
        assert slugify("café") == "cafe"

    def test_long_text_truncated(self):
        result = slugify("a" * 200)
        assert len(result) <= 80


class TestIDGeneration:
    def test_concept_id(self):
        assert concept_id("Volatility Drag") == "concept:volatility-drag"

    def test_principle_id_deterministic(self):
        s = "Higher returns require higher risk"
        assert principle_id(s) == principle_id(s)

    def test_principle_id_different(self):
        assert principle_id("A") != principle_id("B")

    def test_sop_id(self):
        assert sop_id("Portfolio Check") == "sop:portfolio-check"

    def test_reference_id(self):
        assert reference_id("CAPM") == "reference:capm"


# ---------------------------------------------------------------------------
# Coalescence helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_coalesce_definition(self):
        assert _coalesce_definition({"definition": "A"}) == "A"

    def test_coalesce_description_fallback(self):
        assert _coalesce_definition({"description": "B"}) == "B"

    def test_coalesce_definition_preferred(self):
        assert _coalesce_definition({"definition": "A", "description": "B"}) == "A"

    def test_coalesce_empty(self):
        assert _coalesce_definition({}) == ""

    def test_split_used_in_comma(self):
        assert _split_used_in("SOP A, SOP B") == ["SOP A", "SOP B"]

    def test_split_used_in_semicolon(self):
        assert _split_used_in("SOP A; SOP B") == ["SOP A", "SOP B"]

    def test_split_used_in_empty(self):
        assert _split_used_in("") == []


# ---------------------------------------------------------------------------
# Build semantic field
# ---------------------------------------------------------------------------

class TestBuildSemanticField:
    def test_basic_structure(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        assert sf["version"] == "1.0"
        assert sf["source_file"] == "test_video.txt"
        assert "nodes" in sf
        assert "edges" in sf
        assert "metadata" in sf

    def test_concept_nodes_created(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        concepts = [n for n in sf["nodes"] if n["type"] == "concept"]
        assert len(concepts) == 2
        terms = {n["term"] for n in concepts}
        assert "Volatility Drag" in terms
        assert "Sharpe Ratio" in terms

    def test_principle_nodes_created(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        principles = [n for n in sf["nodes"] if n["type"] == "principle"]
        assert len(principles) == 2
        assert principles[0]["epistemic_status"] == "certain"

    def test_sop_nodes_created(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        sops = [n for n in sf["nodes"] if n["type"] == "sop"]
        assert len(sops) == 1
        assert sops[0]["name"] == "Portfolio Check"

    def test_reference_nodes_created(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        refs = [n for n in sf["nodes"] if n["type"] == "reference"]
        assert len(refs) == 2
        names = {n["name"] for n in refs}
        assert "CAPM" in names

    def test_used_in_edge_created(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        used_in = [e for e in sf["edges"] if e["type"] == "used_in"]
        assert len(used_in) >= 1

    def test_references_edge_created(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        refs_edges = [e for e in sf["edges"] if e["type"] == "references"]
        assert len(refs_edges) >= 1

    def test_metadata_counts(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        meta = sf["metadata"]
        assert meta["total_nodes"] == len(sf["nodes"])
        assert meta["total_edges"] == len(sf["edges"])
        assert meta["node_counts"]["concept"] == 2
        assert meta["node_counts"]["principle"] == 2

    def test_empty_compilation(self, empty_compilation):
        sf = build_semantic_field(empty_compilation)
        assert sf["nodes"] == []
        assert sf["edges"] == []
        assert sf["metadata"]["total_nodes"] == 0

    def test_source_metadata_propagated(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        assert sf["source_sha256"] == "abc123"
        assert sf["compiled_at"] == "2026-07-24T23:20:00Z"

    def test_all_nodes_have_source_file(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        for node in sf["nodes"]:
            assert node["source_file"] == "test_video.txt"

    def test_concept_definition_coalesced(self):
        """description field is used as fallback for definition."""
        comp = {
            "source": "test.txt",
            "concepts": [{"term": "X", "description": "desc only"}],
            "principles": [], "sops": [], "references": [],
        }
        sf = build_semantic_field(comp)
        concept = [n for n in sf["nodes"] if n["type"] == "concept"][0]
        assert concept["definition"] == "desc only"

    def test_no_internal_fields_in_output(self, sample_compilation):
        """Internal _used_in_list should not appear in output."""
        sf = build_semantic_field(sample_compilation)
        for node in sf["nodes"]:
            assert "_used_in_list" not in node


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_sf_no_errors(self, sample_compilation):
        sf = build_semantic_field(sample_compilation)
        errors = validate_semantic_field(sf)
        assert errors == []

    def test_missing_node_id(self):
        sf = {"version": "1.0", "nodes": [{"type": "concept", "source_file": "x"}], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert any("missing id" in e.lower() or "Node missing" in e for e in errors)

    def test_invalid_node_type(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "invalid", "source_file": "x"}], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert any("Invalid node type" in e for e in errors)

    def test_invalid_epistemic_status(self):
        sf = {"version": "1.0", "nodes": [{"id": "p1", "type": "principle", "source_file": "x", "epistemic_status": "maybe"}], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert any("Invalid epistemic_status" in e for e in errors)

    def test_duplicate_node_ids(self):
        sf = {"version": "1.0", "nodes": [
            {"id": "c1", "type": "concept", "source_file": "x"},
            {"id": "c1", "type": "concept", "source_file": "x"},
        ], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert any("Duplicate node id" in e for e in errors)

    def test_edge_source_not_in_nodes(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}], "edges": [{"id": "e1", "type": "used_in", "source": "missing", "target": "a"}], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert any("source" in e and "not in nodes" in e for e in errors)

    def test_empty_sf_valid(self):
        sf = {"version": "1.0", "source_file": "x", "built_at": "t", "nodes": [], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert errors == []

    def test_evidence_gate_pass(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x", "evidence_id": "ev1"}], "edges": [], "metadata": {"total_nodes": 1, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf, require_evidence=True)
        assert errors == []

    def test_evidence_gate_fail(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}], "edges": [], "metadata": {"total_nodes": 1, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf, require_evidence=True)
        assert any("missing evidence_id" in e for e in errors)

    def test_evidence_gate_default_off(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}], "edges": [], "metadata": {"total_nodes": 1, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert errors == []

    def test_expanded_edge_type_contradicts(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}, {"id": "b", "type": "concept", "source_file": "x"}], "edges": [{"id": "e1", "type": "contradicts", "source": "a", "target": "b"}], "metadata": {"total_nodes": 2, "total_edges": 1, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert errors == []

    def test_expanded_edge_type_derives_from(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}, {"id": "b", "type": "concept", "source_file": "x"}], "edges": [{"id": "e1", "type": "derives_from", "source": "a", "target": "b"}], "metadata": {"total_nodes": 2, "total_edges": 1, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert errors == []

    def test_invalid_edge_type_still_rejected(self):
        sf = {"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}, {"id": "b", "type": "concept", "source_file": "x"}], "edges": [{"id": "e1", "type": "unknown_type", "source": "a", "target": "b"}], "metadata": {"total_nodes": 2, "total_edges": 1, "node_counts": {}, "edge_counts": {}}}
        errors = validate_semantic_field(sf)
        assert any("Invalid edge type" in e for e in errors)


# ---------------------------------------------------------------------------
# Export: GraphML
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_NETWORKX, reason="networkx not installed")
class TestExportGraphML:
    def test_creates_file(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        path = tmp_path / "test.graphml"
        export_graphml(sf, path)
        assert path.exists()
        content = path.read_text()
        assert "graphml" in content.lower() or "graph" in content.lower()

    def test_empty_sf(self, tmp_path):
        sf = {"version": "1.0", "source_file": "x", "built_at": "t", "nodes": [], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        path = tmp_path / "empty.graphml"
        export_graphml(sf, path)
        assert path.exists()


# ---------------------------------------------------------------------------
# Export: JSON-LD
# ---------------------------------------------------------------------------

class TestExportJSONLD:
    def test_has_context(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        path = tmp_path / "test.jsonld"
        export_jsonld(sf, path)
        data = json.loads(path.read_text())
        assert "@context" in data
        assert "@vocab" in data["@context"]

    def test_roundtrip(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        path = tmp_path / "test.jsonld"
        export_jsonld(sf, path)
        data = json.loads(path.read_text())
        assert len(data["nodes"]) == len(sf["nodes"])
        assert len(data["edges"]) == len(sf["edges"])


# ---------------------------------------------------------------------------
# Export: Markdown
# ---------------------------------------------------------------------------

class TestExportMarkdown:
    def test_has_sections(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        path = tmp_path / "test.md"
        export_markdown(sf, path)
        content = path.read_text()
        assert "## Concepts" in content
        assert "## Principles" in content
        assert "## References" in content

    def test_includes_terms(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        path = tmp_path / "test.md"
        export_markdown(sf, path)
        content = path.read_text()
        assert "Volatility Drag" in content

    def test_empty_sf(self, tmp_path):
        sf = {"version": "1.0", "source_file": "x", "built_at": "t", "nodes": [], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}
        path = tmp_path / "empty.md"
        export_markdown(sf, path)
        assert path.exists()


# ---------------------------------------------------------------------------
# Integration: build + validate + export roundtrip
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_roundtrip(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        errors = validate_semantic_field(sf)
        assert errors == []

        json_path = tmp_path / "sf.json"
        with open(json_path, "w") as f:
            json.dump(sf, f, indent=2)

        if HAS_NETWORKX:
            gml_path = tmp_path / "sf.graphml"
            export_graphml(sf, gml_path)
            assert gml_path.exists()

        ld_path = tmp_path / "sf.jsonld"
        export_jsonld(sf, ld_path)

        md_path = tmp_path / "sf.md"
        export_markdown(sf, md_path)

        assert json_path.exists()
        assert ld_path.exists()
        assert md_path.exists()

    def test_real_compilation_file(self):
        """Test with a real compilation file if available."""
        comp_path = os.path.join(
            os.path.dirname(__file__), "..",
            "output", "quantguild_transcripts", "compilation",
            "kOzvtRE_uX8.txt.json",
        )
        if not os.path.exists(comp_path):
            pytest.skip("Real compilation file not available")

        with open(comp_path) as f:
            comp = json.load(f)

        sf = build_semantic_field(comp)
        errors = validate_semantic_field(sf)
        assert errors == [], f"Validation errors: {errors}"
        assert sf["metadata"]["total_nodes"] > 0
        assert sf["metadata"]["node_counts"].get("concept", 0) > 0


# ---------------------------------------------------------------------------
# Standalone script
# ---------------------------------------------------------------------------

class TestStandaloneScript:
    def test_valid_sf(self, sample_compilation, tmp_path):
        sf = build_semantic_field(sample_compilation)
        sf_path = tmp_path / "sf.json"
        with open(sf_path, "w") as f:
            json.dump(sf, f)

        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/validate_semantic_field.py", str(sf_path)],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert result.returncode == 0
        assert "is valid" in result.stdout

    def test_invalid_sf(self, tmp_path):
        sf_path = tmp_path / "bad.json"
        with open(sf_path, "w") as f:
            json.dump({"version": "2.0", "nodes": [], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}, f)

        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/validate_semantic_field.py", str(sf_path)],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert result.returncode == 1
        assert "failed" in result.stdout.lower()

    def test_require_evidence_flag(self, tmp_path):
        sf_path = tmp_path / "noev.json"
        with open(sf_path, "w") as f:
            json.dump({"version": "1.0", "nodes": [{"id": "a", "type": "concept", "source_file": "x"}], "edges": [], "metadata": {"total_nodes": 1, "total_edges": 0, "node_counts": {}, "edge_counts": {}}}, f)

        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/validate_semantic_field.py", "--require-evidence", str(sf_path)],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert result.returncode == 1
        assert "evidence_id" in result.stdout
