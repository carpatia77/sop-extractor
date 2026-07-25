#!/usr/bin/env python3
"""Emerging Questions Generator — detect gaps, tensions, limits in SF.

Analyzes Semantic Field to find:
  1. Gaps: concepts mentioned but not defined, principles without evidence
  2. Tensions: principles with dissent_type, conflicting concepts
  3. Limits: speculative principles, weak definitions, sparse connections

Output: emerging_questions.json + emerging_questions.md

Standalone module — not yet wired to teach sessions or CLI.
Call generate_emerging_questions(sf) directly for analysis.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def detect_undefined_concepts(sf: dict) -> list[dict]:
    """Find concepts with empty or very short definitions."""
    gaps = []
    for node in sf.get("nodes", []):
        if node.get("type") != "concept":
            continue
        definition = node.get("definition", "")
        if not definition or len(definition) < 10:
            gaps.append({
                "type": "undefined_concept",
                "severity": "medium",
                "node_id": node.get("id", ""),
                "term": node.get("term", ""),
                "question": f"O que significa '{node.get('term', '')}'? Definição ausente ou muito curta.",
            })
    return gaps


def detect_principles_without_evidence(sf: dict) -> list[dict]:
    """Find principles with empty or missing evidence."""
    gaps = []
    for node in sf.get("nodes", []):
        if node.get("type") != "principle":
            continue
        evidence = node.get("evidence", "")
        if not evidence or len(evidence) < 10:
            gaps.append({
                "type": "principle_without_evidence",
                "severity": "high",
                "node_id": node.get("id", ""),
                "statement": node.get("statement", "")[:80],
                "question": f"Qual é a evidência para: '{node.get('statement', '')[:60]}?'",
            })
    return gaps


def detect_sops_without_conditions(sf: dict) -> list[dict]:
    """Find SOPs without 'when_to_use' conditions."""
    gaps = []
    for node in sf.get("nodes", []):
        if node.get("type") != "sop":
            continue
        when = node.get("when_to_use", "")
        if not when or len(when) < 10:
            gaps.append({
                "type": "sop_without_conditions",
                "severity": "medium",
                "node_id": node.get("id", ""),
                "name": node.get("name", ""),
                "question": f"Quando aplicar '{node.get('name', '')}'? Condições de uso ausentes.",
            })
    return gaps


def detect_orphan_concepts(sf: dict) -> list[dict]:
    """Find concepts not connected to any SOP or principle via edges."""
    connected_ids = set()
    for edge in sf.get("edges", []):
        connected_ids.add(edge.get("source", ""))
        connected_ids.add(edge.get("target", ""))

    orphans = []
    for node in sf.get("nodes", []):
        if node.get("type") != "concept":
            continue
        if node.get("id", "") not in connected_ids:
            orphans.append({
                "type": "orphan_concept",
                "severity": "low",
                "node_id": node.get("id", ""),
                "term": node.get("term", ""),
                "question": f"Como '{node.get('term', '')}' se conecta com o resto do conhecimento?",
            })
    return orphans


# ---------------------------------------------------------------------------
# Tension detection
# ---------------------------------------------------------------------------

def detect_refutation_tensions(sf: dict) -> list[dict]:
    """Find principles with active refutation chains (tensions)."""
    tensions = []
    for node in sf.get("nodes", []):
        if node.get("type") != "principle":
            continue
        alt = node.get("strongest_alternative", "")
        if alt:
            tensions.append({
                "type": "refutation_tension",
                "severity": "medium",
                "node_id": node.get("id", ""),
                "statement": node.get("statement", "")[:80],
                "alternative": alt[:80],
                "dissent_type": node.get("dissent_type", "unknown"),
                "question": f"Como resolver a tensão entre '{node.get('statement', '')[:50]}' e '{alt[:50]}'?",
            })
    return tensions


def detect_epistemic_uncertainty(sf: dict) -> list[dict]:
    """Find principles marked as speculative (uncertain knowledge)."""
    uncertainties = []
    for node in sf.get("nodes", []):
        if node.get("type") != "principle":
            continue
        if node.get("epistemic_status") == "speculative":
            uncertainties.append({
                "type": "epistemic_uncertainty",
                "severity": "medium",
                "node_id": node.get("id", ""),
                "statement": node.get("statement", "")[:80],
                "question": f"O que sabemos que não sabemos sobre: '{node.get('statement', '')[:60]}?'",
            })
    return uncertainties


# ---------------------------------------------------------------------------
# Limit detection
# ---------------------------------------------------------------------------

def detect_sparse_connections(sf: dict) -> list[dict]:
    """Find nodes with very few connections (1-2), not 0 (that's orphan).

    Sparse = has some connections but is isolated from the broader graph.
    Orphan (0 connections) is handled by detect_orphan_concepts.
    """
    node_connections: dict[str, int] = {}
    for edge in sf.get("edges", []):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        node_connections[src] = node_connections.get(src, 0) + 1
        node_connections[tgt] = node_connections.get(tgt, 0) + 1

    limits = []
    for node in sf.get("nodes", []):
        nid = node.get("id", "")
        conns = node_connections.get(nid, 0)
        if 1 <= conns <= 2 and node.get("type") in ("concept", "principle"):
            limits.append({
                "type": "sparse_connection",
                "severity": "low",
                "node_id": nid,
                "term": node.get("term") or node.get("statement", "")[:60],
                "question": f"Existem outras perspectivas sobre '{node.get('term') or node.get('statement', '')[:50]}'?",
            })
    return limits


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_emerging_questions(
    sf: dict,
    include_gaps: bool = True,
    include_tensions: bool = True,
    include_limits: bool = True,
) -> dict:
    """Generate emerging questions from Semantic Field analysis.

    Returns dict with:
      - questions: list of question dicts
      - summary: counts by type and severity
      - generated_at: timestamp
    """
    questions = []

    if include_gaps:
        questions.extend(detect_undefined_concepts(sf))
        questions.extend(detect_principles_without_evidence(sf))
        questions.extend(detect_sops_without_conditions(sf))
        questions.extend(detect_orphan_concepts(sf))

    if include_tensions:
        questions.extend(detect_refutation_tensions(sf))
        questions.extend(detect_epistemic_uncertainty(sf))

    if include_limits:
        questions.extend(detect_sparse_connections(sf))

    # Count by type and severity
    type_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    for q in questions:
        t = q.get("type", "unknown")
        s = q.get("severity", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        severity_counts[s] = severity_counts.get(s, 0) + 1

    return {
        "questions": questions,
        "summary": {
            "total": len(questions),
            "by_type": type_counts,
            "by_severity": severity_counts,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_emerging_questions(result: dict, output_dir: str | Path) -> dict:
    """Save emerging questions to JSON + Markdown files.

    Returns dict with file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / "emerging_questions.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Markdown
    md_path = output_dir / "emerging_questions.md"
    questions = result.get("questions", [])
    summary = result.get("summary", {})

    lines = [
        "# Emerging Questions",
        "",
        f"**Generated**: {result.get('generated_at', '?')}",
        f"**Total**: {summary.get('total', 0)} questions",
        "",
    ]

    # Group by severity
    for severity in ["high", "medium", "low"]:
        sev_questions = [q for q in questions if q.get("severity") == severity]
        if sev_questions:
            lines.append(f"## {severity.capitalize()} ({len(sev_questions)})")
            lines.append("")
            for q in sev_questions:
                qtype = q.get("type", "unknown").replace("_", " ")
                lines.append(f"- **[{qtype}]** {q.get('question', '')}")
            lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {"json": str(json_path), "markdown": str(md_path)}


def load_emerging_questions(output_dir: str | Path) -> dict | None:
    """Load existing emerging questions from JSON."""
    path = Path(output_dir) / "emerging_questions.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None
