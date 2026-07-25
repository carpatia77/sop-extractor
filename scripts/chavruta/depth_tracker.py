#!/usr/bin/env python3
"""Depth Tracker — measures debate depth (1-7, chess analogy).

Grounded in observable graph events, NOT LLM subjectivity. Each depth
level corresponds to a specific interaction with the Semantic Field:

  1: Superficial — repeats SF terms without crossing
  2: Comprehension — references 1 node with evidence_id
  3: Analysis — engages disconfirming_evidence
  4: Synthesis — mentions 2+ connected nodes
  5: Evaluation — invokes strongest_alternative
  6: Creation — introduces new term anchored to SF
  7: Meta-cognition — uncertainty markers + SF reference

Monotonicity rule: depth = max(disparados). Order of checks doesn't
affect result.

Used by:
  - Chavruta Engine: reports depth in UI, calibrates next challenge
  - depth_ui: progress bar + chess analogy label
"""
from __future__ import annotations

try:
    from scripts.verify_concept_presence import salient_terms
    from scripts.chavruta.sf_matcher import find_nodes
    from scripts.chavruta.drift_detector import _has_negation
except ImportError:
    from verify_concept_presence import salient_terms
    from chavruta.sf_matcher import find_nodes
    from chavruta.drift_detector import _has_negation


# ---------------------------------------------------------------------------
# Depth labels (chess analogy)
# ---------------------------------------------------------------------------

DEPTH_LABELS = {
    1: "Abertura — reconhece padrões básicos",
    2: "Desenvolvimento — entende o porquê",
    3: "Tática — calcula consequências",
    4: "Posicional — cruza ideias de múltiplos planos",
    5: "Estratégia — avalia trade-offs",
    6: "Criatividade — gera jogadas novas",
    7: "Maestria — compreende o que não sabe",
}

UNCERTAINTY_MARKERS = frozenset({
    "não sei", "nao sei", "não tenho certeza", "nao tenho certeza",
    "isso é suposição", "isso e suposicao", "provavelmente",
    "talvez", "pode ser", "não tenho certeza", "incerto",
    "uncertain", "not sure", "maybe", "perhaps", "might be",
    "suposição", "suposicao", "hipótese", "hipotese",
})


# ---------------------------------------------------------------------------
# Individual depth checks (each returns True/False)
# ---------------------------------------------------------------------------

def _check_depth_1(response_terms: set, sf: dict) -> bool:
    """Depth 1: Response repeats SF terms without crossing.

    Detected when response has terms in SF but doesn't reference
    any specific node, edge, or refutation data.
    """
    # Any overlap with SF terms counts as depth 1
    all_sf_text = " ".join([
        " ".join([n.get("statement", ""), n.get("term", ""), n.get("definition", ""), n.get("name", "")])
        for n in sf.get("nodes", [])
    ])
    sf_terms = set(salient_terms(all_sf_text))
    return bool(response_terms & sf_terms)


def _check_depth_2(response_terms: set, sf: dict) -> bool:
    """Depth 2: Response references a specific node with evidence_id.

    Detected when find_nodes matches at least one node that has
    an evidence_id or entry_id set.
    """
    nodes = find_nodes(" ".join(response_terms), sf, threshold=0.3)
    return any(n.get("evidence_id") or n.get("entry_id") for n in nodes)


def _check_depth_3(response_terms: set, sf: dict) -> bool:
    """Depth 3: Response engages disconfirming_evidence.

    Detected when response terms overlap with any node's
    disconfirming_evidence field.
    """
    for node in sf.get("nodes", []):
        disconfirming = node.get("disconfirming_evidence", "")
        if disconfirming:
            dis_terms = set(salient_terms(disconfirming))
            if dis_terms and response_terms & dis_terms:
                return True
    return False


def _check_depth_4(response_terms: set, sf: dict) -> bool:
    """Depth 4: Response mentions 2+ nodes connected by an edge.

    Detected when find_nodes returns 2+ nodes that share an edge
    in the SF graph.
    """
    nodes = find_nodes(" ".join(response_terms), sf, threshold=0.3)
    if len(nodes) < 2:
        return False

    # Check if any pair of matched nodes is connected by an edge
    matched_ids = {n["id"] for n in nodes}
    for edge in sf.get("edges", []):
        if edge["source"] in matched_ids and edge["target"] in matched_ids:
            return True
    return False


def _check_depth_5(response_terms: set, sf: dict) -> bool:
    """Depth 5: Response invokes strongest_alternative.

    Detected when response terms overlap with any node's
    strongest_alternative field, AND the response is not negating it.
    """
    if _has_negation(" ".join(response_terms)):
        return False  # Negating the alternative is contradiction, not evaluation

    for node in sf.get("nodes", []):
        alt = node.get("strongest_alternative", "")
        if alt:
            alt_terms = set(salient_terms(alt))
            if alt_terms and response_terms & alt_terms:
                return True
    return False


def _check_depth_6(
    response_terms: set,
    sf: dict,
    task_contract: dict | None = None,
    evidence_ledger: dict | None = None,
) -> bool:
    """Depth 6: Response introduces new term anchored to SF.

    Detected when response has terms NOT in the SF, but those
    terms are anchored via:
      1. strongest_alternative
      2. user_goal (salient_terms overlap > 0.3)
      3. evidence_text from Evidence Ledger (anchor #3, ACTIVE in Fase C)
    """
    # Get SF terms
    all_sf_text = " ".join([
        " ".join([n.get("statement", ""), n.get("term", ""), n.get("definition", ""), n.get("name", "")])
        for n in sf.get("nodes", [])
    ])
    sf_terms = set(salient_terms(all_sf_text))

    # Find terms NOT in SF
    new_terms = response_terms - sf_terms
    if not new_terms:
        return False  # All terms are in SF — not creation

    # Check anchor #1: strongest_alternative
    for node in sf.get("nodes", []):
        alt = node.get("strongest_alternative", "")
        if alt:
            alt_terms = set(salient_terms(alt))
            if new_terms & alt_terms:
                return True

    # Check anchor #2: user_goal via salient_terms
    if task_contract:
        user_goal = task_contract.get("user_goal", "")
        goal_terms = set(salient_terms(user_goal))
        if goal_terms:
            overlap = len(new_terms & goal_terms) / len(new_terms | goal_terms)
            if overlap > 0.3:
                return True

    # Check anchor #3: evidence_text from Evidence Ledger (ACTIVE in Fase C)
    if evidence_ledger:
        for entry in evidence_ledger.get("entries", []):
            ev_text = entry.get("evidence_text", "")
            if ev_text:
                ev_terms = set(salient_terms(ev_text))
                if ev_terms and new_terms & ev_terms:
                    return True

    return False


def _check_depth_7(response_terms: set, sf: dict, original_text: str = "") -> bool:
    """Depth 7: Meta-cognition — uncertainty markers + SF reference.

    Detected when response contains uncertainty markers AND
    references SF terms (user knows what they don't know).
    Uses original text for multi-word marker detection.
    """
    # Use original text for multi-word markers ("não sei", "not sure", etc.)
    text_to_check = original_text.lower() if original_text else " ".join(response_terms)
    has_uncertainty = any(marker in text_to_check for marker in UNCERTAINTY_MARKERS)
    if not has_uncertainty:
        return False

    # Must also reference SF terms (not just saying "I don't know" about anything)
    all_sf_text = " ".join([
        " ".join([n.get("statement", ""), n.get("term", ""), n.get("definition", "")])
        for n in sf.get("nodes", [])
    ])
    sf_terms = set(salient_terms(all_sf_text))
    return bool(response_terms & sf_terms)


# ---------------------------------------------------------------------------
# Main depth evaluator
# ---------------------------------------------------------------------------

def evaluate_depth(
    user_response: str,
    sf: dict,
    task_contract: dict | None = None,
    evidence_ledger: dict | None = None,
) -> dict:
    """Evaluate debate depth of a user response.

    Uses observable graph events (node lookups, edge traversal,
    refutation chain invocations) — NOT LLM subjectivity.

    Args:
        user_response: the user's text
        sf: semantic field dict with nodes + edges
        task_contract: optional task contract with user_goal
        evidence_ledger: optional evidence ledger for anchor #3

    Returns:
        dict with keys:
            - depth: int (1-7)
            - label: str (chess analogy)
            - scores: dict mapping each depth level to True/False
            - depth_6_type: str ("creation" or "none") — distinguishes
              from drift when new terms are introduced
    """
    response_terms = set(salient_terms(user_response))
    if not response_terms:
        return {
            "depth": 1,
            "label": DEPTH_LABELS[1],
            "scores": {i: False for i in range(1, 8)},
            "depth_6_type": "none",
        }

    scores = {
        1: _check_depth_1(response_terms, sf),
        2: _check_depth_2(response_terms, sf),
        3: _check_depth_3(response_terms, sf),
        4: _check_depth_4(response_terms, sf),
        5: _check_depth_5(response_terms, sf),
        6: _check_depth_6(response_terms, sf, task_contract, evidence_ledger),
        7: _check_depth_7(response_terms, sf, user_response),
    }

    # Monotonicity: depth = max(disparados)
    fired = [d for d, v in scores.items() if v]
    depth = max(fired) if fired else 1

    # Depth 6 type distinction
    depth_6_type = "creation" if scores[6] else "none"

    return {
        "depth": depth,
        "label": DEPTH_LABELS[depth],
        "scores": scores,
        "depth_6_type": depth_6_type,
    }


def get_depth_label(depth: int) -> str:
    """Get chess analogy label for a depth level."""
    return DEPTH_LABELS.get(depth, DEPTH_LABELS[1])


def depth_bar(depth: int, width: int = 20) -> str:
    """Generate a visual depth bar: ████░░░░░░░░░░░░░░░░ 4/7"""
    filled = int((depth / 7) * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {depth}/7"
