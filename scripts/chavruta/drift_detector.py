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
  3. evidence_text — ACTIVE (Fase C, reads from Evidence Ledger)

Used by:
  - Chavruta Engine: blocks responses that leave the scope
  - depth_tracker.py: distinguishes Depth 6 (creation) from drift
"""
from __future__ import annotations

import re

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

PT_EN_STEM_MAP = {
    "consistencia": "consist", "consistência": "consist", "consistente": "consist",
    "plano": "plan", "planos": "plan",
    "erro": "err", "erros": "err", "errar": "err",
    "risco": "risk", "riscos": "risk",
    "trade": "trade", "trader": "trader", "trading": "trad",
    "mente": "mind", "mental": "mind", "psicologia": "mind",
    "disciplina": "disciplin", "disciplinado": "disciplin",
    "regra": "rule", "regras": "rule",
    "ego": "ego", "emocao": "emot", "emoção": "emot", "emocoes": "emot", "emoções": "emot",
    "processo": "process", "execucao": "execut", "execução": "execut",
    "autor": "author", "metodo": "method", "método": "method",
}


def _stem_term(term: str) -> str:
    t = term.lower()
    if t in PT_EN_STEM_MAP:
        return PT_EN_STEM_MAP[t]
    if len(t) > 4:
        t = re.sub(r'(ção|cao|mente|s|es)$', '', t)
    return t[:5]


def _calculate_coverage(response_terms: set, sf: dict) -> float:
    """Calculate fraction of response terms that exist in the SF with multilingual stem matching."""
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

    mapped = set()
    sf_stems = {_stem_term(st) for st in sf_terms}

    for rt in response_terms:
        if rt in sf_terms:
            mapped.add(rt)
        else:
            r_stem = _stem_term(rt)
            if r_stem in sf_stems:
                mapped.add(rt)

    return len(mapped) / len(response_terms) if response_terms else 0.0


# ---------------------------------------------------------------------------
# Core drift detection
# ---------------------------------------------------------------------------

def detect_drift(
    user_response: str,
    sf: dict,
    task_contract: dict | None = None,
    match_threshold: float = 0.20,
    evidence_ledger: dict | None = None,
) -> dict:
    """Detect if user response drifts from the knowledge scope."""
    # Check meta-questions / clarification
    meta_phrases = ["fora do tema", "como assim", "nao entendi", "não entendi", "qual e o tema", "qual é o tema"]
    is_meta = any(p in user_response.lower() for p in meta_phrases)
    if not is_meta and "?" in user_response:
        resp_lower = user_response.lower().strip()
        if resp_lower.startswith("por que ") or resp_lower.startswith("porque "):
            is_meta = True

    if is_meta:
        return {
            "is_drift": True,
            "is_meta_question": True,
            "is_contradiction": False,
            "confidence": 0.9,
            "reason": "User asking meta question / clarification",
            "matched_nodes": [],
            "anchor_used": "none",
            "semantic_issues": [],
        }

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

    # Anchor #3: evidence_text do Evidence Ledger (ACTIVE in Fase C)
    if anchor == "none" and not is_contradiction and evidence_ledger:
        for entry in evidence_ledger.get("entries", []):
            ev_text = entry.get("evidence_text", "")
            if ev_text and response_terms & set(salient_terms(ev_text)):
                anchor = "evidence_text"
                break

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

    # Semantic guard: secondary defense for subtle errors
    # Only runs if main check passed (not already drift/contradiction)
    semantic_result = {"issues": []}
    if not is_drift:
        try:
            from chavruta.semantic_guard import check_semantic_errors
            semantic_result = check_semantic_errors(user_response, sf)
            # If semantic guard finds high-severity issues, escalate to drift
            if not semantic_result["is_valid"]:
                is_drift = True
                confidence = 0.8
                high_issues = [i for i in semantic_result["issues"] if i["severity"] == "high"]
                reason = f"Semantic error detected: {high_issues[0]['message'][:100]}"
        except ImportError:
            pass  # semantic_guard not available, skip

    return {
        "is_drift": is_drift,
        "is_contradiction": is_contradiction,
        "confidence": round(confidence, 2),
        "reason": reason,
        "matched_nodes": matched_ids,
        "anchor_used": anchor,
        "semantic_issues": semantic_result.get("issues", []),
    }


def is_drift(
    user_response: str,
    sf: dict,
    task_contract: dict | None = None,
    match_threshold: float = 0.25,
    evidence_ledger: dict | None = None,
) -> bool:
    """Simple boolean wrapper around detect_drift."""
    return detect_drift(user_response, sf, task_contract, match_threshold, evidence_ledger)["is_drift"]
