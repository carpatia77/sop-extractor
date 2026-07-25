#!/usr/bin/env python3
"""Semantic Field builder — transforms compile output into a knowledge graph.

Consumes the JSON output from scripts/compile.py and produces:
  - semantic_field.json (structured graph with nodes + edges)
  - graph.graphml (networkx export for visualization)
  - semantic_field.md (human-readable markdown)

Every node carries an evidence_id gate (anti-hallucination).
Every edge carries a type from a fixed enum.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# ID generation (deterministic, content-based)
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug: lowercase, strip accents, replace
    non-alphanumeric with hyphens, collapse runs, strip edges."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:80]


def concept_id(term: str) -> str:
    return f"concept:{slugify(term)}"


def principle_id(statement: str) -> str:
    h = hashlib.sha256(statement.encode()).hexdigest()[:8]
    return f"principle:{h}"


def sop_id(name: str) -> str:
    return f"sop:{slugify(name)}"


def reference_id(name: str) -> str:
    return f"reference:{slugify(name)}"


# ---------------------------------------------------------------------------
# Coalescence helpers
# ---------------------------------------------------------------------------

def _coalesce_definition(concept: dict) -> str:
    """Handle definition/description inconsistency in compile output."""
    return concept.get("definition") or concept.get("description") or ""


def _split_used_in(used_in_raw: str) -> list[str]:
    """Split 'used_in' string into list: handles comma, semicolon, 'e'."""
    if not used_in_raw:
        return []
    parts = re.split(r"[,;]|\be\b", used_in_raw)
    return [s.strip() for s in parts if s.strip()]


# ---------------------------------------------------------------------------
# Edge builder
# ---------------------------------------------------------------------------

def _make_edge_id(counter: list[int]) -> str:
    """Generate edge ID using a mutable counter (no global state)."""
    counter[0] += 1
    return f"edge:{counter[0]:04d}"


def build_edges(
    concept_nodes: list[dict],
    principle_nodes: list[dict],
    sop_nodes: list[dict],
    reference_nodes: list[dict],
) -> list[dict]:
    """Build edges from node cross-references."""
    counter = [0]

    edges = []
    sop_names = {n["name"]: n["id"] for n in sop_nodes}
    ref_names = {n["name"]: n["id"] for n in reference_nodes}

    # Concept → SOP (used_in)
    for node in concept_nodes:
        for sop_name in node.get("_used_in_list", []):
            sop_nid = sop_names.get(sop_name)
            if sop_nid:
                edges.append({
                    "id": _make_edge_id(counter),
                    "type": "used_in",
                    "source": node["id"],
                    "target": sop_nid,
                    "evidence_id": None,
                    "inferred": True,
                })

    # Principle → Reference (references)
    for node in principle_nodes:
        evidence = node.get("evidence", "")
        for ref_name, ref_nid in ref_names.items():
            if ref_name.lower() in evidence.lower():
                edges.append({
                    "id": _make_edge_id(counter),
                    "type": "references",
                    "source": node["id"],
                    "target": ref_nid,
                    "evidence_id": None,
                    "inferred": True,
                })

    # Concept → Reference (references) — via definition/term matching
    for node in concept_nodes:
        text = (node.get("definition", "") + " " + node.get("term", "")).lower()
        for ref_name, ref_nid in ref_names.items():
            if ref_name.lower() in text:
                edges.append({
                    "id": _make_edge_id(counter),
                    "type": "references",
                    "source": node["id"],
                    "target": ref_nid,
                    "evidence_id": None,
                    "inferred": True,
                })

    return edges


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_semantic_field(compilation: dict) -> dict:
    """Transform a compilation JSON into a semantic field graph.

    Args:
        compilation: output from scripts/compile.py (dict with sops, principles, concepts, references)

    Returns:
        Semantic field dict with nodes, edges, metadata.
    """
    # Use source_path (full relative path) for provenance, not source (bare filename).
    # All real ingestion videos have source="transcript.srt" which collapses.
    source_file = compilation.get("source_path") or compilation.get("source", "unknown")
    source_sha256 = compilation.get("source_sha256", "")
    compiled_at = compilation.get("compiled_at", "")

    concept_nodes = []
    for c in compilation.get("concepts", []):
        term = c.get("term", "")
        if not term:
            continue
        nid = concept_id(term)
        definition = _coalesce_definition(c)
        used_in_raw = c.get("used_in", "")
        used_in_list = _split_used_in(used_in_raw)
        concept_nodes.append({
            "id": nid,
            "type": "concept",
            "term": term,
            "definition": definition,
            "source_file": source_file,
            "evidence_id": None,
            "_used_in_list": used_in_list,
        })

    principle_nodes = []
    for p in compilation.get("principles", []):
        statement = p.get("statement", "")
        if not statement:
            continue
        nid = principle_id(statement)
        principle_nodes.append({
            "id": nid,
            "type": "principle",
            "statement": statement,
            "epistemic_status": p.get("epistemic_status", "speculative"),
            "source_file": source_file,
            "evidence_id": f"{source_file}#principle:{len(principle_nodes)}",
            "evidence": p.get("evidence", ""),
        })

    sop_nodes = []
    for s in compilation.get("sops", []):
        name = s.get("name", "")
        if not name:
            continue
        nid = sop_id(name)
        sop_nodes.append({
            "id": nid,
            "type": "sop",
            "name": name,
            "when_to_use": s.get("when_to_use", ""),
            "source_file": source_file,
            "evidence_id": f"{source_file}#sop:{len(sop_nodes)}",
        })

    reference_nodes = []
    for ref in compilation.get("references", []):
        if not ref or not isinstance(ref, str):
            continue
        nid = reference_id(ref)
        reference_nodes.append({
            "id": nid,
            "type": "reference",
            "name": ref,
            "source_file": source_file,
            "evidence_id": None,
        })

    # Build edges
    edges = build_edges(concept_nodes, principle_nodes, sop_nodes, reference_nodes)

    # Remove internal _used_in_list before output
    for n in concept_nodes:
        n.pop("_used_in_list", None)
    # Remove evidence text from principle nodes (it's in the source, not in SF)
    for n in principle_nodes:
        n.pop("evidence", None)

    all_nodes = concept_nodes + principle_nodes + sop_nodes + reference_nodes

    # Metadata
    node_counts = {}
    for n in all_nodes:
        t = n["type"]
        node_counts[t] = node_counts.get(t, 0) + 1

    edge_counts = {}
    for e in edges:
        t = e["type"]
        edge_counts[t] = edge_counts.get(t, 0) + 1

    return {
        "version": "1.0",
        "source_file": source_file,
        "source_sha256": source_sha256,
        "compiled_at": compiled_at,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "nodes": all_nodes,
        "edges": edges,
        "metadata": {
            "total_nodes": len(all_nodes),
            "total_edges": len(edges),
            "node_counts": node_counts,
            "edge_counts": edge_counts,
        },
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALID_EPHEMERAL = {"certain", "probable", "speculative"}
VALID_EDGE_TYPES = {"used_in", "supports", "requires", "references"}
VALID_NODE_TYPES = {"concept", "principle", "sop", "reference"}


def validate_semantic_field(sf: dict) -> list[str]:
    """Validate a semantic field. Returns list of errors (empty = valid)."""
    errors = []

    if sf.get("version") != "1.0":
        errors.append(f"Invalid version: {sf.get('version')}")

    nodes = sf.get("nodes", [])
    edges = sf.get("edges", [])

    node_ids = set()
    for n in nodes:
        nid = n.get("id", "")
        if not nid:
            errors.append(f"Node missing id: {n}")
            continue
        if nid in node_ids:
            errors.append(f"Duplicate node id: {nid}")
        node_ids.add(nid)

        ntype = n.get("type", "")
        if ntype not in VALID_NODE_TYPES:
            errors.append(f"Invalid node type '{ntype}' for node {nid}")

        ep = n.get("epistemic_status")
        if ep is not None and ep not in VALID_EPHEMERAL:
            errors.append(f"Invalid epistemic_status '{ep}' for node {nid}")

        if not n.get("source_file"):
            errors.append(f"Node {nid} missing source_file")

    for e in edges:
        eid = e.get("id", "")
        if not eid:
            errors.append(f"Edge missing id: {e}")
            continue

        etype = e.get("type", "")
        if etype not in VALID_EDGE_TYPES:
            errors.append(f"Invalid edge type '{etype}' for edge {eid}")

        src = e.get("source", "")
        tgt = e.get("target", "")
        if src not in node_ids:
            errors.append(f"Edge {eid} source '{src}' not in nodes")
        if tgt not in node_ids:
            errors.append(f"Edge {eid} target '{tgt}' not in nodes")

    return errors


# ---------------------------------------------------------------------------
# Export: GraphML
# ---------------------------------------------------------------------------

def export_graphml(sf: dict, path: Path) -> None:
    """Export semantic field as GraphML via networkx."""
    try:
        import networkx as nx
    except ImportError:
        raise RuntimeError(
            "networkx is required for GraphML export. "
            "Install with: pip install networkx"
        )

    G = nx.DiGraph()
    for node in sf.get("nodes", []):
        attrs = {k: v for k, v in node.items() if k != "id" and v is not None}
        G.add_node(node["id"], **attrs)
    for edge in sf.get("edges", []):
        attrs = {k: v for k, v in edge.items() if k not in ("id", "source", "target") and v is not None}
        G.add_edge(edge["source"], edge["target"], **attrs)

    nx.write_graphml(G, str(path))


# ---------------------------------------------------------------------------
# Export: JSON-LD
# ---------------------------------------------------------------------------

JSONLD_CONTEXT = {
    "@vocab": "http://schema.org/",
    "semantic_field": "http://xhal2049.org/schema/semantic_field#",
    "epistemic_status": "semantic_field:epistemic_status",
    "evidence_id": "semantic_field:evidence_id",
    "source_file": "semantic_field:source_file",
    "inferred": "semantic_field:inferred",
    "used_in": {"@id": "semantic_field:used_in", "@type": "@id"},
    "supports": {"@id": "semantic_field:supports", "@type": "@id"},
    "requires": {"@id": "semantic_field:requires", "@type": "@id"},
    "references": {"@id": "semantic_field:references", "@type": "@id"},
}


def export_jsonld(sf: dict, path: Path) -> None:
    """Export semantic field as JSON-LD."""
    output = {
        "@context": JSONLD_CONTEXT,
        "nodes": sf.get("nodes", []),
        "edges": sf.get("edges", []),
        "metadata": sf.get("metadata", {}),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Export: Markdown
# ---------------------------------------------------------------------------

def export_markdown(sf: dict, path: Path) -> None:
    """Export semantic field as human-readable markdown."""
    nodes = sf.get("nodes", [])
    edges = sf.get("edges", [])

    concepts = [n for n in nodes if n["type"] == "concept"]
    principles = [n for n in nodes if n["type"] == "principle"]
    sops = [n for n in nodes if n["type"] == "sop"]
    references = [n for n in nodes if n["type"] == "reference"]

    lines = [
        f"# Semantic Field: {sf.get('source_file', 'unknown')}",
        "",
        f"**Built**: {sf.get('built_at', '?')}",
        f"**Nodes**: {len(nodes)} | **Edges**: {len(edges)}",
        "",
    ]

    if concepts:
        lines.append(f"## Concepts ({len(concepts)})")
        lines.append("")
        for c in concepts:
            ep = f" ({c['epistemic_status']})" if c.get("epistemic_status") else ""
            lines.append(f"- **{c['term']}**{ep}: {c.get('definition', '')[:120]}")
        lines.append("")

    if principles:
        lines.append(f"## Principles ({len(principles)})")
        lines.append("")
        for p in principles:
            ep = p.get("epistemic_status", "?")
            lines.append(f"- [{ep}] {p['statement'][:120]}")
        lines.append("")

    if sops:
        lines.append(f"## SOPs ({len(sops)})")
        lines.append("")
        for s in sops:
            lines.append(f"- **{s['name']}**: {s.get('when_to_use', '')[:100]}")
        lines.append("")

    if references:
        lines.append(f"## References ({len(references)})")
        lines.append("")
        for r in references:
            lines.append(f"- {r['name']}")
        lines.append("")

    if edges:
        lines.append(f"## Relationships ({len(edges)})")
        lines.append("")
        for e in edges:
            lines.append(f"- {e['source']} →[{e['type']}]→ {e['target']}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
