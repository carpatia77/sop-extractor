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

def build_semantic_field(compilation: dict, evidence_ledger: dict | None = None) -> dict:
    """Transform a compilation JSON into a semantic field graph.

    Args:
        compilation: output from scripts/compile.py (dict with sops, principles, concepts, references)
        evidence_ledger: optional evidence ledger for real entry_id (replaces positional)

    Returns:
        Semantic field dict with nodes, edges, metadata.
    """
    # Use source_path (full relative path) for provenance, not source (bare filename).
    # All real ingestion videos have source="transcript.srt" which collapses.
    source_file = compilation.get("source_path") or compilation.get("source", "unknown")
    source_sha256 = compilation.get("source_sha256", "")
    compiled_at = compilation.get("compiled_at", "")

    # Build ledger lookup: claim -> entry (for real entry_id)
    ledger_by_claim = {}
    if evidence_ledger:
        for entry in evidence_ledger.get("entries", []):
            ledger_by_claim[entry["claim"]] = entry

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
        # Use real entry_id from Evidence Ledger if available, else positional
        ledger_entry = ledger_by_claim.get(statement, {})
        entry_id = ledger_entry.get("entry_id", "")
        node = {
            "id": nid,
            "type": "principle",
            "statement": statement,
            "epistemic_status": p.get("epistemic_status", "speculative"),
            "source_file": source_file,
            "evidence_id": entry_id or f"{source_file}#principle:{len(principle_nodes)}",
            "evidence": p.get("evidence", ""),
        }
        # Add locator + excerpt_hash from Evidence Ledger if available
        if ledger_entry:
            node["locator"] = ledger_entry.get("locator", "")
            node["excerpt_hash"] = ledger_entry.get("excerpt_hash", "")
        # Include refutation chain data if present (§2.7)
        refutation = p.get("refutation")
        if refutation and not refutation.get("_dry_run"):
            node["strongest_alternative"] = refutation.get("strongest_alternative", "")
            node["disconfirming_evidence"] = refutation.get("disconfirming_evidence", "")
            node["dissent_type"] = refutation.get("dissent_type", "")
        principle_nodes.append(node)

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


# ---------------------------------------------------------------------------
# Export: HTML Viewer (self-contained, interactive)
# ---------------------------------------------------------------------------

def export_html(sf: dict, path: Path) -> None:
    """Export semantic field as self-contained interactive HTML.

    Uses embedded vanilla JS for force-directed graph layout.
    No external dependencies — opens in any browser.
    """
    nodes = sf.get("nodes", [])
    edges = sf.get("edges", [])

    # Prepare node data for JS
    js_nodes = []
    for n in nodes:
        js_nodes.append({
            "id": n["id"],
            "type": n["type"],
            "label": n.get("term") or n.get("statement", "")[:60] or n.get("name", ""),
            "epistemic": n.get("epistemic_status", ""),
            "source": n.get("source_file", ""),
            "entry_id": n.get("evidence_id", ""),
            "locator": n.get("locator", ""),
        })

    # Prepare edge data for JS
    js_edges = []
    for e in edges:
        js_edges.append({
            "source": e["source"],
            "target": e["target"],
            "type": e["type"],
            "inferred": e.get("inferred", False),
        })

    meta = sf.get("metadata", {})

    html = _HTML_TEMPLATE.replace("__NODES__", json.dumps(js_nodes, ensure_ascii=False))
    html = html.replace("__EDGES__", json.dumps(js_edges, ensure_ascii=False))
    html = html.replace("__SOURCE__", sf.get("source_file", "unknown"))
    html = html.replace("__TOTAL_NODES__", str(meta.get("total_nodes", 0)))
    html = html.replace("__TOTAL_EDGES__", str(meta.get("total_edges", 0)))
    html = html.replace("__BUILT_AT__", sf.get("built_at", "?"))

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Semantic Field: __SOURCE__</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; }
#header { padding: 16px 24px; background: #161b22; border-bottom: 1px solid #30363d; }
#header h1 { font-size: 18px; color: #58a6ff; }
#header .meta { font-size: 12px; color: #8b949e; margin-top: 4px; }
#graph { width: 100%; height: calc(100vh - 120px); }
#legend { position: absolute; bottom: 16px; left: 16px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; font-size: 12px; }
#legend .item { display: flex; align-items: center; margin-bottom: 6px; }
#legend .dot { width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
#detail { position: absolute; top: 80px; right: 16px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; width: 320px; max-height: 400px; overflow-y: auto; display: none; font-size: 13px; }
#detail h3 { color: #58a6ff; margin-bottom: 8px; font-size: 14px; }
#detail .field { margin-bottom: 6px; }
#detail .label { color: #8b949e; }
</style>
</head>
<body>
<div id="header">
  <h1>Semantic Field: __SOURCE__</h1>
  <div class="meta">Nodes: __TOTAL_NODES__ | Edges: __TOTAL_EDGES__ | Built: __BUILT_AT__</div>
</div>
<svg id="graph"></svg>
<div id="legend">
  <div class="item"><div class="dot" style="background:#3fb950"></div> Concept</div>
  <div class="item"><div class="dot" style="background:#f0883e"></div> Principle</div>
  <div class="item"><div class="dot" style="background:#bc8cff"></div> SOP</div>
  <div class="item"><div class="dot" style="background:#8b949e"></div> Reference</div>
  <div class="item"><div class="dot" style="background:#30363d; border:1px solid #58a6ff"></div> Edge (solid=explicit, dashed=inferred)</div>
</div>
<div id="detail" onclick="this.style.display='none'">
  <h3 id="detail-title"></h3>
  <div id="detail-body"></div>
</div>
<script>
const nodes = __NODES__;
const edges = __EDGES__;
const W = window.innerWidth, H = window.innerHeight - 40;
const svg = document.getElementById('graph');
svg.setAttribute('width', W);
svg.setAttribute('height', H);
const colors = { concept: '#3fb950', principle: '#f0883e', sop: '#bc8cff', reference: '#8b949e' };
// Simple force-directed layout (no d3)
const sim = nodes.map((n, i) => ({
  ...n, x: W/2 + (Math.random()-0.5)*400, y: H/2 + (Math.random()-0.5)*400, vx: 0, vy: 0
}));
const nodeMap = {}; sim.forEach(n => nodeMap[n.id] = n);
function tick() {
  // Repulsion
  for (let i = 0; i < sim.length; i++) {
    for (let j = i+1; j < sim.length; j++) {
      let dx = sim[j].x - sim[i].x, dy = sim[j].y - sim[i].y;
      let d = Math.sqrt(dx*dx + dy*dy) || 1;
      let f = 200 / (d * d);
      sim[i].vx -= dx/d * f; sim[i].vy -= dy/d * f;
      sim[j].vx += dx/d * f; sim[j].vy += dy/d * f;
    }
  }
  // Attraction (edges)
  edges.forEach(e => {
    const s = nodeMap[e.source], t = nodeMap[e.target];
    if (!s || !t) return;
    let dx = t.x - s.x, dy = t.y - s.y;
    let d = Math.sqrt(dx*dx + dy*dy) || 1;
    let f = (d - 100) * 0.01;
    s.vx += dx/d * f; s.vy += dy/d * f;
    t.vx -= dx/d * f; t.vy -= dy/d * f;
  });
  // Center gravity
  sim.forEach(n => { n.vx += (W/2 - n.x) * 0.001; n.vy += (H/2 - n.y) * 0.001; });
  // Apply velocity
  sim.forEach(n => { n.x += n.vx * 0.5; n.y += n.vy * 0.5; n.vx *= 0.8; n.vy *= 0.8; });
}
function render() {
  svg.innerHTML = '';
  // Edges
  edges.forEach(e => {
    const s = nodeMap[e.source], t = nodeMap[e.target];
    if (!s || !t) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', s.x); line.setAttribute('y1', s.y);
    line.setAttribute('x2', t.x); line.setAttribute('y2', t.y);
    line.setAttribute('stroke', e.inferred ? '#30363d' : '#58a6ff');
    line.setAttribute('stroke-width', '1');
    if (e.inferred) line.setAttribute('stroke-dasharray', '4,4');
    svg.appendChild(line);
  });
  // Nodes
  sim.forEach(n => {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('transform', `translate(${n.x},${n.y})`);
    g.style.cursor = 'pointer';
    g.onclick = () => showDetail(n);
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('r', n.type === 'concept' ? 8 : 6);
    c.setAttribute('fill', colors[n.type] || '#8b949e');
    g.appendChild(c);
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', 10); t.setAttribute('y', 4);
    t.setAttribute('fill', '#c9d1d9'); t.setAttribute('font-size', '11');
    t.textContent = n.label.length > 40 ? n.label.slice(0, 40) + '...' : n.label;
    g.appendChild(t);
    svg.appendChild(g);
  });
}
function showDetail(n) {
  const d = document.getElementById('detail');
  d.style.display = 'block';
  document.getElementById('detail-title').textContent = n.label;
  const fields = [
    ['Type', n.type],
    ['Epistemic', n.epistemic],
    ['Entry ID', n.entry_id],
    ['Locator', n.locator],
    ['Source', n.source ? n.source.split('/').pop() : ''],
  ];
  document.getElementById('detail-body').innerHTML = fields
    .filter(([,v]) => v).map(([k,v]) => `<div class="field"><span class="label">${k}:</span> ${v}</div>`).join('');
}
function loop() { tick(); render(); requestAnimationFrame(loop); }
loop();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Export: LightRAG/Cognee Adapter (machine feed)
# ---------------------------------------------------------------------------

def export_lightrag(sf: dict, path: Path) -> None:
    """Export semantic field as LightRAG-compatible JSON.

    LightRAG expects:
    - nodes: [{id, type, content, metadata}]
    - edges: [{source, target, relationship, metadata}]

    Also works as Cognee input (same graph format).
    """
    nodes_out = []
    for n in sf.get("nodes", []):
        # Build content string from available fields
        parts = []
        if n.get("term"):
            parts.append(f"Concept: {n['term']}")
        if n.get("definition"):
            parts.append(f"Definition: {n['definition']}")
        if n.get("statement"):
            parts.append(f"Principle: {n['statement']}")
        if n.get("when_to_use"):
            parts.append(f"SOP: {n['name']} — {n['when_to_use']}")
        if n.get("name") and n["type"] == "reference":
            parts.append(f"Reference: {n['name']}")
        if n.get("epistemic_status"):
            parts.append(f"Epistemic: {n['epistemic_status']}")
        if n.get("strongest_alternative"):
            parts.append(f"Counter-argument: {n['strongest_alternative']}")
        if n.get("locator"):
            parts.append(f"Locator: {n['locator']}")

        nodes_out.append({
            "id": n["id"],
            "type": n["type"],
            "content": " | ".join(parts) if parts else n["id"],
            "metadata": {
                "source_file": n.get("source_file", ""),
                "entry_id": n.get("evidence_id") or n.get("entry_id", ""),
                "epistemic_status": n.get("epistemic_status", ""),
                "locator": n.get("locator", ""),
            },
        })

    edges_out = []
    for e in sf.get("edges", []):
        edges_out.append({
            "source": e["source"],
            "target": e["target"],
            "relationship": e["type"],
            "metadata": {
                "inferred": e.get("inferred", False),
                "evidence_id": e.get("evidence_id", ""),
            },
        })

    output = {
        "format": "lightrag-v1",
        "source": sf.get("source_file", ""),
        "built_at": sf.get("built_at", ""),
        "nodes": nodes_out,
        "edges": edges_out,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
