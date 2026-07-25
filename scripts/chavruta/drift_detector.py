#!/usr/bin/env python3
"""Drift Detector — detects when user response leaves the knowledge scope.

Uses 2 active anchors (strongest_alternative + user_goal via salient_terms)
to distinguish genuine drift from creative responses. A third anchor
(evidence_text) is unlocked but commented — will be activated in Fase C
when the Chavruta Engine is implemented.

Anchor status:
  1. strongest_alternative — ACTIVE (reads from SF principle nodes)
  2. user_goal via salient_terms overlap > 0.3 — ACTIVE
  3. evidence_text — UNLOCKED (exists in Evidence Ledger) but COMMENTED

Used by:
  - Chavruta Engine: blocks responses that leave the scope
  - depth_tracker.py: distinguishes Depth 6 (creation) from drift
"""
from __future__ import annotations

try:
    from scripts.verify_concept_presence import salient_terms
    from scripts.chavruta.sf_matcher import find_nodes
except ImportError:
    from verify_concept_presence import salient_terms
    from chavruta.sf_matcher import find_nodes


# ---------------------------------------------------------------------------
# Core drift detection
# ---------------------------------------------------------------------------

def detect_drift(
    user_response: str,
    sf: dict,
    task_contract: dict | None = None,
    match_threshold: float = 0.25,
) -> dict:
    """Detect if user response drifts from the knowledge scope.

    Args:
        user_response: the user's text
        sf: semantic field dict with nodes
        task_contract: optional task contract with user_goal
        match_threshold: minimum fraction of response terms that must
            map to SF nodes (default 0.2 = 20%)

    Returns:
        dict with keys:
            - is_drift: bool
            - confidence: float (0-1, how confident we are)
            - reason: str (human-readable explanation)
            - matched_nodes: list of node IDs that matched
            - anchor_used: str (which anchor detected non-drift, or "none")
    """
    response_terms = set(salient_terms(user_response))
    if not response_terms:
        return {
            "is_drift": False,
            "confidence": 0.5,
            "reason": "Response too short to evaluate",
            "matched_nodes": [],
            "anchor_used": "none",
        }

    # Check 1: Do response terms map to SF nodes?
    matched_nodes = find_nodes(user_response, sf, threshold=0.3)
    matched_ids = [n["id"] for n in matched_nodes]

    # Calculate term coverage
    all_sf_text = " ".join([
        " ".join([
            n.get("statement", ""),
            n.get("term", ""),
            n.get("definition", ""),
            n.get("name", ""),
        ])
        for n in sf.get("nodes", [])
    ])
    sf_terms = set(salient_terms(all_sf_text))
    if sf_terms:
        mapped = response_terms & sf_terms
        coverage = len(mapped) / len(response_terms)
    else:
        coverage = 0.0

    # Check 2: Strongest alternative anchor (ACTIVE)
    # Check ALL principle nodes, not just matched ones — anchor is independent
    anchor = "none"
    for node in sf.get("nodes", []):
        alt = node.get("strongest_alternative", "")
        if alt and response_terms & set(salient_terms(alt)):
            anchor = "strongest_alternative"
            matched_ids.append(node["id"])
            break

    # Check 3: User goal anchor via salient_terms (ACTIVE)
    if anchor == "none" and task_contract:
        user_goal = task_contract.get("user_goal", "")
        goal_terms = set(salient_terms(user_goal))
        if goal_terms:
            goal_overlap = len(response_terms & goal_terms) / len(response_terms | goal_terms)
            if goal_overlap > 0.25:
                anchor = "user_goal"

    # FUTURA (Fase C): anchor #3 — evidence_text do Evidence Ledger
    # if anchor == "none":
    #     for entry in evidence_ledger.get("entries", []):
    #         ev_text = entry.get("evidence_text", "")
    #         if ev_text and response_terms & set(salient_terms(ev_text)):
    #             anchor = "evidence_text"
    #             break

    # Decision
    is_drift = coverage < match_threshold and anchor == "none"
    confidence = min(1.0, coverage + (0.3 if anchor != "none" else 0.0))

    if is_drift:
        reason = f"Only {coverage:.0%} of response terms map to SF, no anchor found"
    elif anchor != "none":
        reason = f"Anchored via {anchor} (coverage: {coverage:.0%})"
    else:
        reason = f"Terms map to SF (coverage: {coverage:.0%})"

    return {
        "is_drift": is_drift,
        "confidence": round(confidence, 2),
        "reason": reason,
        "matched_nodes": matched_ids,
        "anchor_used": anchor,
    }


def is_drift(
    user_response: str,
    sf: dict,
    task_contract: dict | None = None,
    match_threshold: float = 0.25,
) -> bool:
    """Simple boolean wrapper around detect_drift."""
    return detect_drift(user_response, sf, task_contract, match_threshold)["is_drift"]
