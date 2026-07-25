#!/usr/bin/env python3
"""Drift Detector — detects when user response leaves the knowledge scope.

Uses 2 active anchors (strongest_alternative + user_goal via salient_terms)
to distinguish genuine drift from creative responses. A third anchor
(evidence_text) is unlocked but commented — will be activated in Fase C
when the Chavruta Engine is implemented.

Critical design rule: lexical overlap alone does NOT prevent drift.
A response that uses SF terms but NEGATES them (e.g. "drag does NOT
compound") is a contradiction, not an anchor. The detector checks for
negation words and disconfirming_evidence matches before granting anchor.

Anchor status:
  1. strongest_alternative — ACTIVE (reads from SF principle nodes)
  2. user_goal via salient_terms overlap > 0.25 — ACTIVE
  3. evidence_text — UNLOCKED (exists in Evidence Ledger) but COMMENTED

Used by:
  - Chavruta Engine: blocks responses that leave the scope
  - depth_tracker.py: distinguishes Depth 6 (creation) from drift
"""
from __future__ import annotations

try:
    from scripts.verify_concept_presence import salient_terms
except ImportError:
    from verify_concept_presence import salient_terms


# ---------------------------------------------------------------------------
# Negation detection
# ---------------------------------------------------------------------------

NEGATION_WORDS = frozenset({
    "not", "never", "no", "neither", "nor", "nobody", "nothing",
    "nowhere", "nor", "cannot", "can't", "don't", "doesn't", "didn't",
    "won't", "wouldn't", "shouldn't", "couldn't", "isn't", "aren't",
    "wasn't", "weren't", "hasn't", "haven't", "hadn't",
    "wrong", "myth", "false", "useless", "broken", "fake",
    "fail", "fails", "failed", "flawed", "flaw",
})

# Words that signal the user is CHALLENGING the claim, not affirming it
CHALLENGE_WORDS = frozenset({
    "wrong", "myth", "false", "useless", "broken", "fake",
    "fails", "failed", "flawed", "flaw", "disprove", "refute",
    "contradict", "contrary", "opposite",
    "disagree", "disagreement", "incorrect",
})


def _has_negation(text: str) -> bool:
    """Check if text contains negation words."""
    words = set(text.lower().split())
    return bool(words & NEGATION_WORDS)


def _has_challenge(text: str) -> bool:
    """Check if text contains challenge words (user is disputing a claim)."""
    words = set(text.lower().split())
    return bool(words & CHALLENGE_WORDS)


def _contradicts_principle(response: str, sf: dict) -> bool:
    """Check if response directly contradicts a principle via disconfirming_evidence.

    If the user's response matches a principle's disconfirming_evidence,
    they are explicitly challenging the principle — NOT anchoring to it.
    """
    response_terms = set(salient_terms(response))
    for node in sf.get("nodes", []):
        if node.get("type") != "principle":
            continue
        # Check if response matches disconfirming_evidence
        disconfirming = node.get("disconfirming_evidence", "")
        if disconfirming:
            dis_terms = set(salient_terms(disconfirming))
            if dis_terms and response_terms & dis_terms:
                # User is voicing the counter-argument — this is a challenge
                return True
        # Check if response negates the principle's statement
        statement = node.get("statement", "")
        if statement:
            st_terms = set(salient_terms(statement))
            if st_terms and response_terms & st_terms and _has_negation(response):
                # User uses SF terms but negates them — contradiction
                return True
            # Check if response challenges the principle's statement
            if st_terms and response_terms & st_terms and _has_challenge(response):
                # User uses SF terms and challenge words — contradiction
                return True
    return False


# ---------------------------------------------------------------------------
# Coverage calculation
# ---------------------------------------------------------------------------

def _calculate_coverage(response_terms: set, sf: dict) -> float:
    """Calculate fraction of response terms that exist in the SF.

    Returns 0.0-1.0 where 1.0 means all response terms are in the SF.
    """
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
    if not sf_terms:
        return 0.0
    mapped = response_terms & sf_terms
    return len(mapped) / len(response_terms) if response_terms else 0.0


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
            map to SF nodes (default 0.25 = 25%)

    Returns:
        dict with keys:
            - is_drift: bool — True if response is outside knowledge scope
            - confidence: float (0-1) — when is_drift=True: how sure we are
              it's genuine drift (higher = more likely drift). When
              is_drift=False: how strongly the response is anchored to SF
              (higher = more grounded).
            - reason: str (human-readable explanation)
            - matched_nodes: list of node IDs that matched (annotation only)
            - anchor_used: str (which anchor detected non-drift, or "none")
            - is_contradiction: bool — True if response contradicts SF content
    """
    response_terms = set(salient_terms(user_response))
    if not response_terms:
        return {
            "is_drift": False,
            "is_contradiction": False,
            "confidence": 0.5,
            "reason": "Response too short to evaluate",
            "matched_nodes": [],
            "anchor_used": "none",
        }

    # Calculate term coverage (how much of the response maps to SF)
    coverage = _calculate_coverage(response_terms, sf)

    # Check: does response CONTRADICT the SF? (negation or challenge)
    is_contradiction = _contradicts_principle(user_response, sf)

    # Check: strongest_alternative anchor (ACTIVE)
    # If response matches a principle's disconfirming_evidence, it's a
    # CHALLENGE, not an anchor — skip this check for contradictions.
    anchor = "none"
    if not is_contradiction:
        for node in sf.get("nodes", []):
            alt = node.get("strongest_alternative", "")
            if alt and response_terms & set(salient_terms(alt)):
                # Double-check: is the user affirming or negating the alternative?
                if not _has_negation(user_response) and not _has_challenge(user_response):
                    anchor = "strongest_alternative"
                    break

    # Check: user_goal anchor via salient_terms (ACTIVE)
    if anchor == "none" and task_contract and not is_contradiction:
        user_goal = task_contract.get("user_goal", "")
        goal_terms = set(salient_terms(user_goal))
        if goal_terms:
            goal_overlap = len(response_terms & goal_terms) / len(response_terms | goal_terms)
            if goal_overlap > 0.25:
                anchor = "user_goal"

    # FUTURA (Fase C): anchor #3 — evidence_text do Evidence Ledger
    # if anchor == "none" and not is_contradiction:
    #     for entry in evidence_ledger.get("entries", []):
    #         ev_text = entry.get("evidence_text", "")
    #         if ev_text and response_terms & set(salient_terms(ev_text)):
    #             anchor = "evidence_text"
    #             break

    # Decision: contradiction always overrides anchor
    if is_contradiction:
        is_drift = True
        confidence = min(1.0, 0.7 + (0.3 if _has_challenge(user_response) else 0.0))
        reason = f"Contradicts SF content (negation/challenge detected, coverage: {coverage:.0%})"
    elif coverage < match_threshold and anchor == "none":
        is_drift = True
        confidence = min(1.0, 1.0 - coverage)
        reason = f"Only {coverage:.0%} of response terms map to SF, no anchor found"
    else:
        is_drift = False
        confidence = min(1.0, coverage + (0.3 if anchor != "none" else 0.0))
        reason = f"Anchored via {anchor} (coverage: {coverage:.0%})" if anchor != "none" else f"Terms map to SF (coverage: {coverage:.0%})"

    # matched_nodes: annotation only (from find_nodes), doesn't affect decision
    from chavruta.sf_matcher import find_nodes as _find
    matched_nodes = _find(user_response, sf, threshold=0.3)
    matched_ids = [n["id"] for n in matched_nodes]

    return {
        "is_drift": is_drift,
        "is_contradiction": is_contradiction,
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
