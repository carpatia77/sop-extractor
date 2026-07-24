#!/usr/bin/env python3
"""Mandatory sampling review gate for batch compilation (§2.5).

Risk-weighted sampling pauses batch compilation for operator review.
Reject aborts the remaining batch by default; --continue-on-reject opts in.

Sampling priorities (in order):
  1. First item of every batch (calibration baseline)
  2. Low coherence-audit confidence items
  3. re_candidate items (structurally complex, higher misread risk)
  4. Longest sources (most surface area for subtle error)
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone


def compute_sample_indices(
    n_items: int,
    sample_rate: float = 0.10,
    confidence_scores: list[float] | None = None,
    re_candidates: list[bool] | None = None,
    source_lengths: list[int] | None = None,
    confidence_threshold: float = 0.60,
) -> list[int]:
    """Compute which batch indices get sampled for human review.

    Risk-weighted, not uniform random. Returns sorted list of 0-based indices.

    Priority order:
      1. Index 0 (first item — calibration baseline)
      2. Items with confidence < threshold
      3. Items flagged re_candidate
      4. Longest sources (top N by char count)
    """
    if n_items <= 0 or sample_rate <= 0:
        return []

    n_sample = max(1, math.ceil(n_items * sample_rate))
    # Cap at total items
    n_sample = min(n_sample, n_items)

    selected = set()

    # Priority 1: first item (always sampled if budget allows)
    if n_sample > 0:
        selected.add(0)

    # Priority 2: low confidence items
    if confidence_scores:
        low_conf = [
            i for i, c in enumerate(confidence_scores)
            if c < confidence_threshold and i not in selected
        ]
        for i in low_conf:
            if len(selected) >= n_sample:
                break
            selected.add(i)

    # Priority 3: re_candidate items
    if re_candidates:
        re_items = [
            i for i, rc in enumerate(re_candidates)
            if rc and i not in selected
        ]
        for i in re_items:
            if len(selected) >= n_sample:
                break
            selected.add(i)

    # Priority 4: longest sources (fill remaining budget)
    if source_lengths and len(selected) < n_sample:
        indexed = [
            (i, length) for i, length in enumerate(source_lengths)
            if i not in selected
        ]
        indexed.sort(key=lambda x: x[1], reverse=True)
        for i, _ in indexed:
            if len(selected) >= n_sample:
                break
            selected.add(i)

    # Fill any remaining budget with sequential indices
    if len(selected) < n_sample:
        for i in range(n_items):
            if len(selected) >= n_sample:
                break
            selected.add(i)

    return sorted(selected)


def present_for_review(
    index: int,
    total: int,
    filename: str,
    sections: dict,
    source_content: str,
    max_excerpt: int = 500,
) -> str:
    """Build a human-readable review prompt for a sampled compilation item.

    Shows compiled output alongside a source excerpt for each claimed principle.
    """
    lines = [
        f"{'='*60}",
        f"REVIEW GATE — item {index + 1}/{total}: {filename}",
        f"{'='*60}",
        "",
    ]

    # SOPs
    if sections.get("sops"):
        lines.append(f"## SOPs ({len(sections['sops'])})")
        for sop in sections["sops"]:
            lines.append(f"  - {sop.get('name', '?')}")
            for step in sop.get("steps", [])[:3]:
                lines.append(f"    {step}")
            if sop.get("when_to_use"):
                lines.append(f"    When: {sop['when_to_use']}")
        lines.append("")

    # Principles with source excerpts
    if sections.get("principles"):
        lines.append(f"## Principles ({len(sections['principles'])})")
        for p in sections["principles"]:
            score = p.get("_grounding_score")
            score_str = f" [grounding: {score:.0%}]" if score is not None else ""
            lines.append(f"  - {p.get('statement', '?')}{score_str}")
            lines.append(f"    Epistemic: {p.get('epistemic_status', '?')}")
            if p.get("evidence"):
                lines.append(f"    Evidence: {p['evidence'][:120]}")
        lines.append("")

    # Concepts
    if sections.get("concepts"):
        lines.append(f"## Concepts ({len(sections['concepts'])})")
        for c in sections["concepts"][:10]:
            lines.append(f"  - {c.get('term', '?')}: {c.get('definition', '?')[:80]}")
        lines.append("")

    # Source excerpt
    excerpt = source_content[:max_excerpt]
    if len(source_content) > max_excerpt:
        excerpt += "..."
    lines.append(f"## Source excerpt ({len(source_content):,} chars total)")
    lines.append(excerpt)
    lines.append("")

    lines.append("Decision: [A]pprove / [R]eject / [E]dit > ")
    return "\n".join(lines)


def prompt_operator(
    index: int,
    total: int,
    filename: str,
    sections: dict,
    source_content: str,
) -> dict:
    """Present compiled output to operator and collect decision.

    Returns {"verdict": "approve"|"reject"|"edit", "timestamp": ..., "editor": ...}
    """
    review_text = present_for_review(index, total, filename, sections, source_content)
    print(review_text)

    while True:
        try:
            choice = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[Interrupted — treating as reject]")
            return {
                "verdict": "reject",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "editor": os.environ.get("USER", "unknown"),
            }

        if choice in ("a", "approve", "y", "yes", ""):
            return {
                "verdict": "approve",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "editor": os.environ.get("USER", "unknown"),
            }
        elif choice in ("r", "reject", "n", "no"):
            return {
                "verdict": "reject",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "editor": os.environ.get("USER", "unknown"),
            }
        elif choice in ("e", "edit"):
            print("  Edit notes (empty line to finish):")
            edits = []
            while True:
                try:
                    line = input()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line.strip():
                    break
                edits.append(line)
            return {
                "verdict": "edit",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "editor": os.environ.get("USER", "unknown"),
                "edit_notes": "\n".join(edits),
            }
        else:
            print("  Enter A (approve), R (reject), or E (edit):")


def record_review(
    review_log: list[dict],
    index: int,
    filename: str,
    decision: dict,
) -> None:
    """Append a review decision to the review log.

    The log gets written to run.json as part of batch provenance.
    """
    review_log.append({
        "index": index,
        "filename": filename,
        "sampled": True,
        **decision,
    })


def record_not_reviewed(
    review_log: list[dict],
    index: int,
    filename: str,
) -> None:
    """Record that an item was not sampled for review."""
    review_log.append({
        "index": index,
        "filename": filename,
        "sampled": False,
    })


def should_abort_batch(review_log: list[dict], continue_on_reject: bool) -> bool:
    """Check if the batch should be aborted based on review decisions.

    Returns True if any reject was found AND --continue-on-reject was not set.
    """
    if continue_on_reject:
        return False
    return any(r.get("verdict") == "reject" for r in review_log)
