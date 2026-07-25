#!/usr/bin/env python3
"""Cross-Analysis consolidator — merges N semantic fields into one unified graph.

Reads compilation JSONs from a directory, builds semantic fields in memory,
and produces a consolidated cross-video analysis:
  - Multi-video consolider (merged graph with frequency counts)
  - Theme detector (concept co-occurrence clustering)
  - Gold extractor (concepts unique to few videos)
  - Link suggester (missing edges across videos)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from semantic_field import build_semantic_field, slugify


# ---------------------------------------------------------------------------
# Load compilations from directory
# ---------------------------------------------------------------------------

def load_compilations(directory: Path | str) -> list[dict]:
    """Load all compilation JSONs from a directory (excluding run.json, semantic fields)."""
    directory = Path(directory)
    compilations = []
    comp_dir = directory / "compilation" if (directory / "compilation").is_dir() else directory
    for f in sorted(comp_dir.glob("*.json")):
        if f.name == "run.json" or "semantic_field" in f.name or "batch_summary" in f.name:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if "concepts" in data or "principles" in data:
                compilations.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return compilations


# ---------------------------------------------------------------------------
# Consolidation — merge N semantic fields
# ---------------------------------------------------------------------------

def consolidate(compilations: list[dict]) -> dict:
    """Build semantic fields from compilations and merge into one unified graph.

    Returns consolidated graph with frequency tracking.
    """
    # Build individual SFs
    sfs = []
    for comp in compilations:
        sf = build_semantic_field(comp)
        sfs.append(sf)

    # Merge nodes — deduplicate by normalized term/statement, track frequency
    concept_freq = Counter()  # term_slug → count of videos
    principle_freq = Counter()  # statement_slug → count
    concept_videos = defaultdict(set)  # term_slug → set of source_files
    principle_videos = defaultdict(set)
    concept_data = {}  # term_slug → latest node data
    principle_data = {}

    for sf in sfs:
        source = sf.get("source_file", "")
        for node in sf.get("nodes", []):
            if node["type"] == "concept":
                key = slugify(node.get("term", ""))
                concept_freq[key] += 1
                concept_videos[key].add(source)
                concept_data[key] = node
            elif node["type"] == "principle":
                key = slugify(node.get("statement", ""))
                principle_freq[key] += 1
                principle_videos[key].add(source)
                principle_data[key] = node

    # Build consolidated nodes
    consolidated_nodes = []
    for key, count in concept_freq.items():
        node = concept_data[key].copy()
        node["id"] = f"concept:{key}"
        node["frequency"] = count
        node["source_files"] = sorted(concept_videos[key])
        consolidated_nodes.append(node)

    for key, count in principle_freq.items():
        node = principle_data[key].copy()
        node["id"] = f"principle:{key}"
        node["frequency"] = count
        node["source_files"] = sorted(principle_videos[key])
        consolidated_nodes.append(node)

    # Cross-video edges — concept co-occurrence + per-video explicit edges
    cross_edges = []
    edge_counter = 0
    pair_index = {}  # sorted_pair → edge index (for co_occurs dedup)
    explicit_edges = []  # per-video used_in/references edges, carried forward

    for sf in sfs:
        source = sf.get("source_file", "")
        source_basename = Path(source).stem if source else ""

        # Get concepts in this video
        video_concepts = [
            slugify(n.get("term", ""))
            for n in sf.get("nodes", [])
            if n["type"] == "concept"
        ]

        # Create co-occurrence edges
        for i, c1 in enumerate(video_concepts):
            for c2 in video_concepts[i + 1:]:
                pair = tuple(sorted([c1, c2]))
                if pair in pair_index:
                    idx = pair_index[pair]
                    if source not in cross_edges[idx]["source_files"]:
                        cross_edges[idx]["source_files"].append(source)
                else:
                    pair_index[pair] = edge_counter
                    cross_edges.append({
                        "id": f"edge:{edge_counter:04d}",
                        "type": "co_occurs",
                        "source": f"concept:{pair[0]}",
                        "target": f"concept:{pair[1]}",
                        "source_files": [source],
                        "inferred": True,
                    })
                    edge_counter += 1

        # Carry forward per-video explicit edges (used_in, references)
        for e in sf.get("edges", []):
            explicit_edges.append({
                "id": f"edge:{edge_counter:04d}",
                "type": e["type"],
                "source": e["source"],
                "target": e["target"],
                "source_video": source_basename,
                "inferred": False,
            })
            edge_counter += 1

    # Metadata
    node_counts = Counter(n["type"] for n in consolidated_nodes)
    n_concepts = sum(1 for n in consolidated_nodes if n["type"] == "concept")

    return {
        "version": "1.0",
        "type": "cross_analysis",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "total_sources": len(sfs),
        "source_files": [sf.get("source_file", "") for sf in sfs],
        "nodes": consolidated_nodes,
        "edges": cross_edges,
        "explicit_edges": explicit_edges,
        "metadata": {
            "total_nodes": len(consolidated_nodes),
            "total_edges": len(cross_edges),
            "total_explicit_edges": len(explicit_edges),
            "node_counts": dict(node_counts),
            "n_concepts": n_concepts,
            "n_principles": sum(1 for n in consolidated_nodes if n["type"] == "principle"),
        },
    }


# ---------------------------------------------------------------------------
# Theme detection — concept co-occurrence clustering
# ---------------------------------------------------------------------------

def detect_themes(consolidated: dict, min_cooccurrence: int = 2) -> list[dict]:
    """Detect themes from concept co-occurrence across videos.

    A theme is a group of concepts that co-occur in multiple videos.
    """
    edges = consolidated.get("edges", [])
    concepts = {n["id"]: n for n in consolidated.get("nodes", []) if n["type"] == "concept"}

    # Build adjacency from co-occurrence edges
    adj = defaultdict(set)
    for e in edges:
        if e["type"] == "co_occurs" and len(e.get("source_files", [])) >= min_cooccurrence:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])

    # Simple clustering: connected components with sufficient co-occurrence
    visited = set()
    themes = []
    for node_id in sorted(adj.keys()):
        if node_id in visited:
            continue
        # BFS
        component = set()
        queue = [node_id]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(component) >= 2:
            # Name theme by most frequent concept
            members = []
            for cid in component:
                node = concepts.get(cid, {})
                members.append({
                    "id": cid,
                    "term": node.get("term", cid.replace("concept:", "")),
                    "frequency": node.get("frequency", 0),
                })
            members.sort(key=lambda x: x["frequency"], reverse=True)
            theme_name = members[0]["term"]

            themes.append({
                "name": theme_name,
                "members": [m["id"] for m in members],
                "member_terms": [m["term"] for m in members],
                "size": len(component),
                "total_frequency": sum(m["frequency"] for m in members),
            })

    themes.sort(key=lambda t: t["total_frequency"], reverse=True)
    return themes


# ---------------------------------------------------------------------------
# Gold extractor — unique/rare concepts
# ---------------------------------------------------------------------------

def extract_gold(consolidated: dict, max_videos: int = 2) -> list[dict]:
    """Extract gold (unique/rare) concepts that appear in few videos.

    These are the differentiated knowledge — concepts that SÓ appear
    in specific videos, not widespread across the corpus.
    """
    nodes = consolidated.get("nodes", [])
    total_sources = consolidated.get("total_sources", 1)

    gold = []
    for n in nodes:
        if n["type"] != "concept":
            continue
        freq = n.get("frequency", 0)
        if freq <= max_videos:
            rarity = 1.0 - (freq / total_sources) if total_sources > 0 else 1.0
            gold.append({
                "id": n["id"],
                "term": n.get("term", ""),
                "definition": n.get("definition", ""),
                "frequency": freq,
                "rarity_score": round(rarity, 3),
                "source_files": n.get("source_files", []),
                "epistemic_status": n.get("epistemic_status"),
            })

    gold.sort(key=lambda x: x["rarity_score"], reverse=True)
    return gold


# ---------------------------------------------------------------------------
# Link suggester — missing edges across videos
# ---------------------------------------------------------------------------

def suggest_links(consolidated: dict, min_cooccurrence: int = 3) -> list[dict]:
    """Suggest missing links between concepts that co-occur frequently
    across videos but don't already share a target (SOP or reference)
    in any individual video's semantic field.

    Two concepts are "already related" if they both point to the same SOP
    (used_in) or the same reference in any video. We derive these pairs
    from explicit_edges, then filter co_occurs against them.
    """
    import itertools

    edges = consolidated.get("edges", [])
    explicit_edges = consolidated.get("explicit_edges", [])
    nodes = consolidated.get("nodes", [])
    concepts = {n["id"]: n for n in nodes if n["type"] == "concept"}

    # Derive concept pairs that are already related via shared targets.
    # Two concepts sharing a SOP or reference are "already related".
    target_concepts = defaultdict(set)
    for e in explicit_edges:
        src = e["source"]
        tgt = e["target"]
        if src.startswith("concept:"):
            target_concepts[tgt].add(src)

    explicit_pairs = set()
    for concepts_sharing_target in target_concepts.values():
        for a, b in itertools.combinations(sorted(concepts_sharing_target), 2):
            explicit_pairs.add((a, b))

    # Co-occurrence frequency from cross-video analysis
    cooccur = Counter()
    for e in edges:
        if e["type"] == "co_occurs" and len(e.get("source_files", [])) >= min_cooccurrence:
            pair = tuple(sorted([e["source"], e["target"]]))
            cooccur[pair] = len(e.get("source_files", []))

    # Suggest links for frequent co-occurrences NOT already related
    suggestions = []
    for pair, count in cooccur.most_common(20):
        if pair not in explicit_pairs:
            c1 = concepts.get(pair[0], {})
            c2 = concepts.get(pair[1], {})
            suggestions.append({
                "source": pair[0],
                "target": pair[1],
                "source_term": c1.get("term", pair[0]),
                "target_term": c2.get("term", pair[1]),
                "co_occurrence_count": count,
                "suggested_type": "related_to",
            })

    return suggestions


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def generate_report(
    consolidated: dict,
    themes: list[dict],
    gold: list[dict],
    links: list[dict],
) -> str:
    """Generate a markdown report of the cross-analysis."""
    lines = [
        "# Cross-Analysis Report",
        "",
        f"**Built**: {consolidated.get('built_at', '?')}",
        f"**Sources**: {consolidated.get('total_sources', 0)} videos",
        "",
        "## Corpus Overview",
        "",
        f"- **Total nodes**: {consolidated['metadata']['total_nodes']}",
        f"- **Total edges**: {consolidated['metadata']['total_edges']}",
        f"- **Concepts**: {consolidated['metadata']['n_concepts']}",
        f"- **Principles**: {consolidated['metadata']['n_principles']}",
        "",
    ]

    # Most frequent concepts
    concepts = [n for n in consolidated.get("nodes", []) if n["type"] == "concept"]
    concepts.sort(key=lambda x: x.get("frequency", 0), reverse=True)
    lines.append("## Most Frequent Concepts")
    lines.append("")
    lines.append("| Concept | Frequency | Videos |")
    lines.append("|---------|-----------|--------|")
    for c in concepts[:15]:
        vids_raw = c.get("source_files", [])[:3]
        vids = ", ".join(Path(v).stem for v in vids_raw)
        if len(c.get("source_files", [])) > 3:
            vids += f" +{len(c['source_files']) - 3}"
        lines.append(f"| {c.get('term', '?')} | {c.get('frequency', 0)} | {vids} |")
    lines.append("")

    # Themes
    if themes:
        lines.append(f"## Themes ({len(themes)})")
        lines.append("")
        for t in themes[:10]:
            terms = ", ".join(t["member_terms"][:5])
            lines.append(f"- **{t['name']}** ({t['size']} concepts, freq={t['total_frequency']}): {terms}")
        lines.append("")

    # Gold
    if gold:
        lines.append(f"## Gold — Unique/Rare Concepts ({len(gold)})")
        lines.append("")
        for g in gold[:10]:
            lines.append(f"- **{g['term']}** (rarity={g['rarity_score']:.2f}, freq={g['frequency']}): {g['definition'][:80]}")
        lines.append("")

    # Suggested links
    if links:
        lines.append(f"## Suggested Links ({len(links)})")
        lines.append("")
        for l in links[:10]:
            lines.append(f"- {l['source_term']} ↔ {l['target_term']} (co-occurs in {l['co_occurrence_count']} videos)")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_cross_analysis(directory: Path, output_dir: Path | None = None) -> dict:
    """Run full cross-analysis on a directory of compilations."""
    compilations = load_compilations(directory)
    if not compilations:
        print(f"No compilations found in {directory}")
        return {}

    print(f"Loaded {len(compilations)} compilations")

    consolidated = consolidate(compilations)
    themes = detect_themes(consolidated)
    gold = extract_gold(consolidated)
    links = suggest_links(consolidated)

    report = generate_report(consolidated, themes, gold, links)

    # Write output
    if output_dir is None:
        output_dir = directory / "compilation"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write consolidated graph
    graph_path = output_dir / "cross_analysis.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump({
            "consolidated": consolidated,
            "themes": themes,
            "gold": gold,
            "suggested_links": links,
        }, f, indent=2, ensure_ascii=False)

    # Write report
    report_path = output_dir / "cross_analysis.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Cross-analysis: {consolidated['metadata']['total_nodes']} nodes, "
          f"{consolidated['metadata']['total_edges']} edges")
    print(f"Themes: {len(themes)}, Gold: {len(gold)}, Links: {len(links)}")
    print(f"Written: {graph_path.name}, {report_path.name}")

    return {
        "consolidated": consolidated,
        "themes": themes,
        "gold": gold,
        "links": links,
        "report": report,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/quantguild_transcripts")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    run_cross_analysis(directory, output_dir)
