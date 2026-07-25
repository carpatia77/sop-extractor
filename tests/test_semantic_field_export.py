#!/usr/bin/env python3
"""Tests for semantic_field.py exporters — HTML Viewer + LightRAG Adapter.

Tests: export_html produces valid HTML, export_lightrag produces valid JSON,
integration with compile pipeline, edge cases.
"""
import json
import os

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from semantic_field import (
    build_semantic_field,
    export_html,
    export_lightrag,
    export_graphml,
    export_jsonld,
    export_markdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_compilation():
    return {
        "source": "test_video.txt",
        "source_path": "output/test_video.txt",
        "source_sha256": "abc123",
        "compiled_at": "2026-07-25T10:00:00Z",
        "sops": [
            {"name": "Build Portfolio", "steps": ["Step 1"], "when_to_use": "When investing"},
        ],
        "principles": [
            {
                "statement": "Volatility drag compounds against you",
                "epistemic_status": "certain",
                "evidence": "Author states volatility drag compounds",
                "refutation": {
                    "strongest_alternative": "Rebalancing can mitigate drag",
                    "disconfirming_evidence": "Would be false if Sharpe ratio path-independent",
                    "dissent_type": "qualifies",
                },
            },
        ],
        "concepts": [
            {"term": "Volatility Drag", "definition": "Geometric underperformance", "used_in": "Build Portfolio"},
        ],
        "references": ["Sharpe (1966)"],
    }


@pytest.fixture
def sample_sf(sample_compilation):
    return build_semantic_field(sample_compilation)


# ---------------------------------------------------------------------------
# HTML Viewer
# ---------------------------------------------------------------------------

class TestExportHtml:
    def test_creates_html_file(self, sample_sf, tmp_path):
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_contains_header(self, sample_sf, tmp_path):
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        content = out.read_text()
        assert "Semantic Field:" in content
        assert "test_video.txt" in content

    def test_contains_nodes_json(self, sample_sf, tmp_path):
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        content = out.read_text()
        # Should contain the nodes array as JSON
        assert '"id"' in content
        assert '"type"' in content

    def test_contains_edges_json(self, sample_sf, tmp_path):
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        content = out.read_text()
        assert '"source"' in content
        assert '"target"' in content

    def test_contains_legend(self, sample_sf, tmp_path):
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        content = out.read_text()
        assert "Concept" in content
        assert "Principle" in content
        assert "SOP" in content
        assert "Reference" in content

    def test_contains_force_directed_layout(self, sample_sf, tmp_path):
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        content = out.read_text()
        assert "requestAnimationFrame" in content
        assert "tick" in content

    def test_empty_sf(self, tmp_path):
        sf = {"nodes": [], "edges": [], "metadata": {"total_nodes": 0, "total_edges": 0}}
        out = tmp_path / "empty.html"
        export_html(sf, out)
        assert out.exists()
        content = out.read_text()
        assert "Nodes: 0" in content

    def test_self_contained_no_external_deps(self, sample_sf, tmp_path):
        """HTML should not reference external CSS/JS files."""
        out = tmp_path / "test.html"
        export_html(sample_sf, out)
        content = out.read_text()
        assert "src=" not in content or content.count("src=") == 0
        assert "href=" not in content or "stylesheet" not in content


# ---------------------------------------------------------------------------
# LightRAG Adapter
# ---------------------------------------------------------------------------

class TestExportLightrag:
    def test_creates_json_file(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        assert out.exists()

    def test_valid_json(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        with open(out) as f:
            data = json.load(f)
        assert data["format"] == "lightrag-v1"

    def test_nodes_have_required_fields(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        with open(out) as f:
            data = json.load(f)
        for node in data["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "content" in node
            assert "metadata" in node

    def test_edges_have_required_fields(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        with open(out) as f:
            data = json.load(f)
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "relationship" in edge

    def test_node_content_includes_key_fields(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        with open(out) as f:
            data = json.load(f)
        # Find the concept node
        concept = [n for n in data["nodes"] if n["type"] == "concept"][0]
        assert "Volatility Drag" in concept["content"]
        assert "Definition:" in concept["content"]

    def test_sop_content_includes_name_without_when_to_use(self, tmp_path):
        """Regression: a SOP node's content collapsed to its bare id
        (e.g. 'sop:build-portfolio') whenever when_to_use was empty, because
        the SOP name was only appended alongside when_to_use. LightRAG/Cognee
        retrieval relies on 'content' — a nameless SOP is invisible to search."""
        comp = {
            "source_path": "v1.txt",
            "sops": [{"name": "Build Portfolio", "when_to_use": ""}],
            "principles": [], "concepts": [], "references": [],
        }
        sf = build_semantic_field(comp)
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sf, out)
        with open(out) as f:
            data = json.load(f)
        sop = [n for n in data["nodes"] if n["type"] == "sop"][0]
        assert "Build Portfolio" in sop["content"]
        assert sop["content"] != sop["id"]

    def test_principle_content_includes_refutation(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        with open(out) as f:
            data = json.load(f)
        # Find the principle node
        principle = [n for n in data["nodes"] if n["type"] == "principle"][0]
        assert "Rebalancing" in principle["content"]

    def test_metadata_populated(self, sample_sf, tmp_path):
        out = tmp_path / "test.lightrag.json"
        export_lightrag(sample_sf, out)
        with open(out) as f:
            data = json.load(f)
        assert data["source"] == "output/test_video.txt"
        assert data["built_at"] != ""

    def test_empty_sf(self, tmp_path):
        sf = {"nodes": [], "edges": [], "metadata": {}}
        out = tmp_path / "empty.lightrag.json"
        export_lightrag(sf, out)
        with open(out) as f:
            data = json.load(f)
        assert data["nodes"] == []
        assert data["edges"] == []


# ---------------------------------------------------------------------------
# Existing exporters still work
# ---------------------------------------------------------------------------

class TestExistingExporters:
    def test_export_graphml(self, sample_sf, tmp_path):
        out = tmp_path / "test.graphml"
        try:
            export_graphml(sample_sf, out)
            assert out.exists()
        except RuntimeError:
            pytest.skip("networkx not installed")

    def test_export_jsonld(self, sample_sf, tmp_path):
        out = tmp_path / "test.jsonld"
        export_jsonld(sample_sf, out)
        assert out.exists()
        with open(out) as f:
            data = json.load(f)
        assert "@context" in data

    def test_export_markdown(self, sample_sf, tmp_path):
        out = tmp_path / "test.md"
        export_markdown(sample_sf, out)
        assert out.exists()
        content = out.read_text()
        assert "# Semantic Field:" in content
