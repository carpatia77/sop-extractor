#!/usr/bin/env python3
"""Semantic Guard — catches subtle semantic errors that drift_detector misses.

While drift_detector catches lexical contradictions (negation, challenge words),
this module catches:
  1. Quantitative type confusion (numbers with wrong units/magnitudes)
  2. Definition drift (redefining established concepts)
  3. Scope expansion (extending claims beyond their evidence)

Uses rules-based detection — no embeddings required.

Used by:
  - Chavruta Engine: secondary defense after drift_detector
"""
from __future__ import annotations

import re

try:
    from scripts.verify_concept_presence import salient_terms
except ImportError:
    from verify_concept_presence import salient_terms


# ---------------------------------------------------------------------------
# Quantitative claim detection
# ---------------------------------------------------------------------------

# Patterns for numbers with units (supports comma as thousands separator: 1,600)
NUMBER_UNIT_RE = re.compile(
    r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*'  # number (with optional comma-groups)
    r'(GB|MB|KB|TB|bytes|bps|Hz|MHz|GHz|'  # digital units
    r'snapshots?|frames?|pixels?|bits|chars?|lines?|rows?|entries?|records?|'  # data units
    r'seconds?|minutes?|hours?|days?|ms|ns|μs)',  # time units
    re.IGNORECASE
)

# Patterns for comparison claims
COMPARISON_RE = re.compile(
    r'(more|less|greater|smaller|fewer|faster|slower|higher|lower|'
    r'maior|menor|mais|menos|rápido|lento)\s+',
    re.IGNORECASE
)


def extract_quantitative_claims(text: str) -> list[dict]:
    """Extract claims that involve numbers with units.

    Returns list of {number, unit, context}.
    """
    claims = []
    for match in NUMBER_UNIT_RE.finditer(text):
        number = float(match.group(1).replace(",", ""))
        unit = match.group(2)
        # Get surrounding context (50 chars before and after)
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        context = text[start:end]
        claims.append({
            "number": number,
            "unit": unit,
            "context": context,
            "span": (match.start(), match.end()),
        })
    return claims


def check_quantitative_consistency(
    response: str,
    sf: dict,
    threshold: float = 0.5,
) -> list[dict]:
    """Check if quantitative claims in response are consistent with SF.

    Checks two things:
    1. Same unit with different magnitude (10x+ difference)
    2. Same concept context but different unit type (type confusion)

    Returns list of potential issues: [{type, message, severity, evidence}]
    """
    issues = []
    response_claims = extract_quantitative_claims(response)

    for claim in response_claims:
        number = claim["number"]
        unit = claim["unit"]
        context = claim["context"]

        for node in sf.get("nodes", []):
            statement = node.get("statement", "")
            if not statement:
                continue

            sf_claims = extract_quantitative_claims(statement)
            for sf_claim in sf_claims:
                sf_num = sf_claim["number"]
                sf_unit = sf_claim["unit"]

                # Check 1: Same unit, different magnitude (10x+ difference)
                if sf_unit.lower() == unit.lower():
                    if sf_num > 0 and number > 0:
                        ratio = max(number, sf_num) / min(number, sf_num)
                        if ratio >= 10:
                            issues.append({
                                "type": "quantitative_mismatch",
                                "severity": "high",
                                "message": (
                                    f"Response claims {number} {unit} but SF states "
                                    f"{sf_num} {sf_unit} — {ratio:.0f}x difference"
                                ),
                                "evidence": context,
                                "sf_claim": sf_claim["context"],
                            })

                # Check 2: Different unit type for same concept (type confusion)
                # The most dangerous semantic error: "1.6GB" (storage) confused
                # with "1,600 snapshots" (count) for the same system/entity.
                elif _units_are_incompatible(unit, sf_unit):
                    ctx_terms = set(salient_terms(context))
                    sf_ctx_terms = set(salient_terms(sf_claim["context"]))
                    overlap = ctx_terms & sf_ctx_terms if ctx_terms and sf_ctx_terms else set()
                    # Filter out generic domain words that appear in almost any
                    # technical claim — they're too weak to establish "same concept".
                    # Specific terms (e.g. "volatility drag") still count.
                    _GENERIC_OVERLAP = {
                        "system", "process", "file", "data", "value", "thing",
                        "use", "run", "set", "get", "make", "take", "put",
                        "total", "per", "each", "the", "is", "are", "was",
                    }
                    meaningful_overlap = overlap - _GENERIC_OVERLAP
                    if meaningful_overlap:
                        issues.append({
                            "type": "type_confusion",
                            "severity": "high",
                            "message": (
                                f"Possible type confusion: response uses {number} {unit} "
                                f"but SF states {sf_num} {sf_unit} — different unit types "
                                f"for same concept"
                            ),
                            "evidence": context,
                            "sf_claim": sf_claim["context"],
                        })

    return issues


def _units_are_incompatible(unit1: str, unit2: str) -> bool:
    """Check if two unit types are incompatible (can't be compared)."""
    # Group units by physical category
    # ms/ns/μs are the same quantity as seconds (time) — just different scales
    digital = {"gb", "mb", "kb", "tb", "bytes", "bps", "bits", "chars", "lines", "rows", "entries", "records", "gigabyte", "megabyte", "kilobyte", "terabyte"}
    count = {"snapshots", "snapshot", "frames", "frame", "pixels", "pixel", "entries", "entry", "records", "record", "samples", "sample"}
    time = {"seconds", "second", "minutes", "minute", "hours", "hour", "days", "day", "ms", "ns", "μs", "us"}
    frequency = {"hz", "mhz", "ghz", "khz"}

    def _categorize(u: str) -> str:
        u = u.lower()
        if u in digital:
            return "digital"
        if u in count:
            return "count"
        if u in frequency:
            return "frequency"
        if u in time:
            return "time"
        # Fallback: strip trailing "s" for plural detection
        stripped = u.rstrip("s")
        if stripped in digital:
            return "digital"
        if stripped in count:
            return "count"
        if stripped in frequency:
            return "frequency"
        if stripped in time:
            return "time"
        return "other"

    cat1 = _categorize(unit1)
    cat2 = _categorize(unit2)

    # Different categories = incompatible (including frequency ≠ time)
    return cat1 != cat2 and cat1 != "other" and cat2 != "other"


# ---------------------------------------------------------------------------
# Definition drift detection
# ---------------------------------------------------------------------------

def check_definition_drift(response: str, sf: dict, threshold: float = 0.3) -> list[dict]:
    """Check if response redefines concepts established in the SF.

    Returns list of potential definition drifts.
    """
    issues = []
    response_terms = set(salient_terms(response))

    for node in sf.get("nodes", []):
        if node.get("type") != "concept":
            continue
        term = node.get("term", "")
        definition = node.get("definition", "")
        if not term or not definition:
            continue

        # Check if the user mentions the term but with a different definition
        term_salient = set(salient_terms(term))
        if term_salient and response_terms & term_salient:
            # User mentions this concept — check if they redefine it
            # Look for definition-like patterns
            redef_patterns = [
                r'(is|are|means?|refers?\s+to|defined?\s+as|é|significa|refere[- ]se\s+a)',
            ]
            for pattern in redef_patterns:
                if re.search(pattern, response, re.IGNORECASE):
                    # User is defining this term — check if it matches SF
                    # Simple heuristic: if response doesn't contain key SF terms, it's drift
                    def_salient = set(salient_terms(definition))
                    overlap = len(response_terms & def_salient) / max(len(def_salient), 1)
                    if overlap < threshold:
                        issues.append({
                            "type": "definition_drift",
                            "severity": "medium",
                            "message": (
                                f"Response redefines '{term}' but doesn't match "
                                f"SF definition: '{definition[:80]}'"
                            ),
                            "evidence": response[:200],
                        })

    return issues


# ---------------------------------------------------------------------------
# Scope expansion detection
# ---------------------------------------------------------------------------

def check_scope_expansion(response: str, sf: dict) -> list[dict]:
    """Check if response extends claims beyond their evidence.

    Looks for universal quantifiers (always, never, all, every) applied
    to claims that are conditional in the SF.
    """
    issues = []
    response_terms = set(salient_terms(response))
    universal_quantifiers = re.compile(
        r'\b(always|never|all|every|any|always|sempre|nunca|todos|todas|qualquer)\b',
        re.IGNORECASE
    )

    if not universal_quantifiers.search(response):
        return issues

    # Check if the SF has conditional/qualified versions of these claims
    for node in sf.get("nodes", []):
        if node.get("type") != "principle":
            continue
        statement = node.get("statement", "")
        epistemic = node.get("epistemic_status", "")
        dissent = node.get("dissent_type", "")

        # If the SF says this is qualified/speculative, but response uses universal
        if epistemic in ("speculative",) or dissent in ("qualifies", "context_limited"):
            st_terms = set(salient_terms(statement))
            if st_terms and response_terms & st_terms:
                issues.append({
                    "type": "scope_expansion",
                    "severity": "medium",
                    "message": (
                        f"Response makes universal claim about concept that SF "
                        f"qualifies as '{epistemic}' with dissent '{dissent}'"
                    ),
                    "evidence": response[:200],
                })

    return issues


# ---------------------------------------------------------------------------
# Combined semantic check
# ---------------------------------------------------------------------------

def check_semantic_errors(response: str, sf: dict) -> dict:
    """Run all semantic checks and return combined results.

    Returns dict with:
        - is_valid: bool (no high-severity issues)
        - issues: list of all issues found
        - quantitative: list of quantitative issues
        - definition_drift: list of definition drift issues
        - scope_expansion: list of scope expansion issues
    """
    quantitative = check_quantitative_consistency(response, sf)
    definition_drift = check_definition_drift(response, sf)
    scope_expansion = check_scope_expansion(response, sf)

    all_issues = quantitative + definition_drift + scope_expansion
    has_high = any(i["severity"] == "high" for i in all_issues)

    return {
        "is_valid": not has_high,
        "issues": all_issues,
        "quantitative": quantitative,
        "definition_drift": definition_drift,
        "scope_expansion": scope_expansion,
    }
