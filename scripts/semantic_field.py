#!/usr/bin/env python3
"""Semantic Field builder — transforms compile output into a knowledge graph.

Consumes the JSON output from scripts/compile.py and produces:
  - semantic_field.json (structured graph with nodes + edges)
  - graph.graphml (networkx export for visualization)
  - semantic_field.md (human-readable markdown)

Principle and sop nodes carry evidence_id (anti-hallucination gate).
Edges carry a type from a fixed enum (used_in, supports, requires,
references).  Refutation data (dissent_type, strongest_alternative,
disconfirming_evidence) lives on principle nodes, not as edges.
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


_EVIDENCE_REQUIRED_TYPES = {"principle", "sop"}


def validate_semantic_field(sf: dict, *, require_evidence: bool = False) -> list[str]:
    """Validate a semantic field. Returns list of errors (empty = valid).

    Args:
        sf: Semantic field dict to validate.
        require_evidence: If True, principle and sop nodes missing
            ``evidence_id`` are flagged as errors (anti-hallucination gate).
            Concept and reference nodes are excluded — they legitimately
            lack individual evidence anchors.
    """
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

        if require_evidence and ntype in _EVIDENCE_REQUIRED_TYPES and not n.get("evidence_id"):
            errors.append(f"Node {nid} missing evidence_id (anti-hallucination gate)")

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
<title>xHAL2049 — __SOURCE__</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Share Tech Mono',monospace;background:#06060c;color:#e0e0e0;overflow:hidden}
#grid{position:fixed;inset:0;background-image:
  linear-gradient(rgba(0,212,255,.03) 1px,transparent 1px),
  linear-gradient(90deg,rgba(0,212,255,.03) 1px,transparent 1px);
  background-size:40px 40px;pointer-events:none;z-index:0}
#header{position:fixed;top:0;left:0;right:0;padding:12px 24px;
  background:linear-gradient(180deg,rgba(6,6,12,.95),rgba(6,6,12,.7));
  border-bottom:1px solid rgba(0,212,255,.15);z-index:10;
  display:flex;align-items:center;justify-content:space-between}
#header h1{font-family:'Orbitron',sans-serif;font-size:16px;letter-spacing:3px;
  background:linear-gradient(90deg,#00d4ff,#7b2ff7,#ff0080);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
#header .meta{font-size:11px;color:#555;letter-spacing:1px}
#graph{position:fixed;inset:0;z-index:1}
#legend{position:fixed;bottom:16px;left:16px;
  background:rgba(10,10,18,.9);border:1px solid rgba(0,212,255,.2);
  border-radius:8px;padding:14px 16px;font-size:11px;z-index:10;
  backdrop-filter:blur(8px)}
#legend .item{display:flex;align-items:center;margin-bottom:8px;color:#888}
#legend .dot{width:10px;height:10px;border-radius:50%;margin-right:10px;
  box-shadow:0 0 8px currentColor}
#legend .edge-sample{display:flex;align-items:center;margin-top:10px;padding-top:8px;
  border-top:1px solid #1a1a2e}
#legend .line{width:30px;height:2px;margin-right:10px}
#detail{position:fixed;top:70px;right:16px;
  background:rgba(10,10,18,.92);border:1px solid rgba(123,47,247,.3);
  border-radius:10px;padding:20px;width:340px;max-height:70vh;
  overflow-y:auto;display:none;font-size:12px;z-index:10;
  backdrop-filter:blur(12px);box-shadow:0 0 30px rgba(123,47,247,.1)}
#detail h3{font-family:'Orbitron',sans-serif;font-size:13px;
  color:#00d4ff;margin-bottom:12px;letter-spacing:1px}
#detail .field{margin-bottom:8px;line-height:1.5}
#detail .label{color:#555;font-size:10px;letter-spacing:1px;text-transform:uppercase}
#detail .value{color:#e0e0e0}
#stats{position:fixed;bottom:16px;right:16px;
  background:rgba(10,10,18,.9);border:1px solid rgba(0,212,255,.15);
  border-radius:8px;padding:10px 14px;font-size:10px;color:#555;z-index:10;
  letter-spacing:1px}
</style>
</head>
<body>
<div id="grid"></div>
<div id="header">
  <h1>xHAL2049</h1>
  <div class="meta">__SOURCE__ &nbsp;|&nbsp; __TOTAL_NODES__ nodes &nbsp;|&nbsp; __TOTAL_EDGES__ edges &nbsp;|&nbsp; __BUILT_AT__</div>
</div>
<svg id="graph"></svg>
<div id="legend">
  <div class="item"><div class="dot" style="color:#00ff88;background:#00ff88"></div>Concept</div>
  <div class="item"><div class="dot" style="color:#ff0080;background:#ff0080"></div>Principle</div>
  <div class="item"><div class="dot" style="color:#7b2ff7;background:#7b2ff7"></div>SOP</div>
  <div class="item"><div class="dot" style="color:#ffaa00;background:#ffaa00"></div>Reference</div>
  <div class="edge-sample">
    <div class="line" style="background:linear-gradient(90deg,#00d4ff,#7b2ff7)"></div>
    <span style="color:#666">explicit edge</span>
  </div>
  <div class="edge-sample">
    <div class="line" style="background:repeating-linear-gradient(90deg,#555 0,#555 4px,transparent 4px,transparent 8px)"></div>
    <span style="color:#666">inferred edge</span>
  </div>
</div>
<div id="detail" onclick="this.style.display='none'">
  <h3 id="detail-title"></h3>
  <div id="detail-body"></div>
</div>
<div id="stats">drag nodes &nbsp;|&nbsp; click for detail</div>
<script>
const nodes = __NODES__;
const edges = __EDGES__;
const W = window.innerWidth, H = window.innerHeight;
const svg = document.getElementById('graph');
svg.setAttribute('width', W);
svg.setAttribute('height', H);

const palette = {
  concept:    { fill: '#00ff88', glow: '#00ff88', r: 10 },
  principle:  { fill: '#ff0080', glow: '#ff0080', r: 8 },
  sop:        { fill: '#7b2ff7', glow: '#7b2ff7', r: 8 },
  reference:  { fill: '#ffaa00', glow: '#ffaa00', r: 6 },
};

// SVG defs for glow filters and gradients
const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
defs.innerHTML = `
  <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/>
    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="glow-strong"><feGaussianBlur stdDeviation="6" result="blur"/>
    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <linearGradient id="edge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#00d4ff" stop-opacity="0.6"/>
    <stop offset="100%" stop-color="#7b2ff7" stop-opacity="0.6"/>
  </linearGradient>
`;
svg.appendChild(defs);

// Force simulation
const sim = nodes.map((n, i) => ({
  ...n, x: W/2 + (Math.random()-0.5)*500, y: H/2 + (Math.random()-0.5)*400, vx: 0, vy: 0
}));
const nodeMap = {}; sim.forEach(n => nodeMap[n.id] = n);

// Drag state
let dragNode = null, dragOff = {x:0, y:0};

function tick() {
  if (dragNode) return; // pause physics while dragging
  // Repulsion
  for (let i = 0; i < sim.length; i++) {
    for (let j = i+1; j < sim.length; j++) {
      let dx = sim[j].x - sim[i].x, dy = sim[j].y - sim[i].y;
      let d = Math.sqrt(dx*dx + dy*dy) || 1;
      let f = 300 / (d * d);
      sim[i].vx -= dx/d * f; sim[i].vy -= dy/d * f;
      sim[j].vx += dx/d * f; sim[j].vy += dy/d * f;
    }
  }
  // Edge attraction
  edges.forEach(e => {
    const s = nodeMap[e.source], t = nodeMap[e.target];
    if (!s || !t) return;
    let dx = t.x - s.x, dy = t.y - s.y;
    let d = Math.sqrt(dx*dx + dy*dy) || 1;
    let f = (d - 150) * 0.008;
    s.vx += dx/d * f; s.vy += dy/d * f;
    t.vx -= dx/d * f; t.vy -= dy/d * f;
  });
  // Center gravity
  sim.forEach(n => { n.vx += (W/2 - n.x) * 0.0005; n.vy += (H/2 - n.y) * 0.0005; });
  // Damping
  sim.forEach(n => { n.x += n.vx * 0.6; n.y += n.vy * 0.6; n.vx *= 0.85; n.vy *= 0.85; });
}

function render() {
  // Clear everything except defs
  while (svg.childNodes.length > 1) svg.removeChild(svg.lastChild);

  // Edge glow layer
  const edgeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  edges.forEach(e => {
    const s = nodeMap[e.source], t = nodeMap[e.target];
    if (!s || !t) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', s.x); line.setAttribute('y1', s.y);
    line.setAttribute('x2', t.x); line.setAttribute('y2', t.y);
    if (e.inferred) {
      line.setAttribute('stroke', '#555');
      line.setAttribute('stroke-width', '1');
      line.setAttribute('stroke-dasharray', '6,4');
      line.setAttribute('opacity', '0.5');
    } else {
      line.setAttribute('stroke', 'url(#edge-grad)');
      line.setAttribute('stroke-width', '1.5');
      line.setAttribute('filter', 'url(#glow)');
    }
    edgeGroup.appendChild(line);
  });
  svg.appendChild(edgeGroup);

  // Node layer
  const nodeGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  sim.forEach(n => {
    const p = palette[n.type] || palette.reference;
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('transform', `translate(${n.x},${n.y})`);
    g.style.cursor = 'grab';

    // Outer glow ring
    const ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    ring.setAttribute('r', p.r + 6);
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', p.glow);
    ring.setAttribute('stroke-width', '1');
    ring.setAttribute('opacity', '0.2');
    ring.setAttribute('filter', 'url(#glow-strong)');
    g.appendChild(ring);

    // Main circle
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('r', p.r);
    c.setAttribute('fill', p.fill);
    c.setAttribute('filter', 'url(#glow)');
    c.setAttribute('opacity', '0.9');
    g.appendChild(c);

    // Label
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', p.r + 8);
    t.setAttribute('y', 4);
    t.setAttribute('fill', '#aaa');
    t.setAttribute('font-size', '11');
    t.setAttribute('font-family', 'Share Tech Mono, monospace');
    const label = n.label.length > 45 ? n.label.slice(0, 45) + '...' : n.label;
    t.textContent = label;
    g.appendChild(t);

    // Drag handlers
    g.onmousedown = (ev) => {
      ev.stopPropagation();
      dragNode = n;
      dragOff = { x: ev.clientX - n.x, y: ev.clientY - n.y };
      g.style.cursor = 'grabbing';
    };
    g.onclick = (ev) => { ev.stopPropagation(); showDetail(n); };

    nodeGroup.appendChild(g);
  });
  svg.appendChild(nodeGroup);
}

function showDetail(n) {
  const d = document.getElementById('detail');
  d.style.display = 'block';
  const p = palette[n.type] || palette.reference;
  document.getElementById('detail-title').textContent = n.label;
  document.getElementById('detail-title').style.color = p.fill;
  const fields = [
    ['Type', n.type.toUpperCase()],
    ['Epistemic', n.epistemic],
    ['Entry ID', n.entry_id],
    ['Locator', n.locator],
    ['Source', n.source ? n.source.split('/').pop() : ''],
  ];
  document.getElementById('detail-body').innerHTML = fields
    .filter(([,v]) => v)
    .map(([k,v]) => `<div class="field"><div class="label">${k}</div><div class="value">${v}</div></div>`)
    .join('');
}

// Drag events
svg.onmousemove = (ev) => {
  if (!dragNode) return;
  dragNode.x = ev.clientX - dragOff.x;
  dragNode.y = ev.clientY - dragOff.y;
  dragNode.vx = 0; dragNode.vy = 0;
};
svg.onmouseup = () => { dragNode = null; };
svg.onmouseleave = () => { dragNode = null; };

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
        if n.get("name") and n["type"] == "sop":
            sop_line = f"SOP: {n['name']}"
            if n.get("when_to_use"):
                sop_line += f" — {n['when_to_use']}"
            parts.append(sop_line)
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
