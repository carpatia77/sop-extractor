#!/usr/bin/env python3
"""Evidence Ledger — provenance per claim with locator and excerpt.

Builds a structured ledger of evidence entries from compiled principles.
Each entry links a claim to its source location (SRT timestamp or line
number), the supporting excerpt text, and a deterministic entry_id.

Used by:
  - compile.py: builds ledger during compilation
  - semantic_field.py: uses entry_id for real provenance (replaces positional)
  - depth_tracker.py: anchor #3 for Depth-6/Drift tiebreaker (via evidence_text)

Usage:
    from evidence_ledger import build_ledger, parse_srt_with_timestamps
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# SRT parsing (timestamps)
# ---------------------------------------------------------------------------

_SRT_CUE_RE = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"
    r"(.+?)(?=\n\n|\n\d+\s*\n|\Z)",
    re.DOTALL,
)


def parse_srt_with_timestamps(srt_text: str) -> list[dict]:
    """Parse SRT text into cues with timestamps.

    Returns list of dicts: [{index, start, end, text}, ...]
    """
    cues = []
    for m in _SRT_CUE_RE.finditer(srt_text):
        cues.append({
            "index": int(m.group(1)),
            "start": m.group(2).replace(",", "."),
            "end": m.group(3).replace(",", "."),
            "text": m.group(4).strip(),
        })
    return cues


# ---------------------------------------------------------------------------
# Locator extraction
# ---------------------------------------------------------------------------

def _find_locator_for_evidence(evidence: str, cues: list[dict]) -> str:
    """Find SRT cue whose text contains the evidence excerpt.

    Uses substring match on first 100 chars of evidence.
    Returns timestamp range like "00:12:34.000-00:13:02.000".
    """
    if not evidence or not cues:
        return ""
    evidence_lower = evidence.lower()[:100]
    for cue in cues:
        if evidence_lower in cue["text"].lower():
            return f"{cue['start']}-{cue['end']}"
    return ""


def _find_line_locator(evidence: str, text: str) -> str:
    """Find line number containing the evidence excerpt in a text file.

    Returns "line:N" format.
    """
    if not evidence:
        return ""
    evidence_lower = evidence.lower()[:100]
    for i, line in enumerate(text.splitlines(), 1):
        if evidence_lower in line.lower():
            return f"line:{i}"
    return ""


def extract_locator(evidence: str, source_path: str, original_text: str = "") -> str:
    """Extract locator from source file.

    For SRT files: returns timestamp range.
    For TXT/MD files: returns line number.
    """
    if not evidence:
        return ""

    is_srt = source_path.lower().endswith(".srt")

    if is_srt and original_text:
        cues = parse_srt_with_timestamps(original_text)
        return _find_locator_for_evidence(evidence, cues)
    elif original_text:
        return _find_line_locator(evidence, original_text)
    elif not is_srt:
        # Fallback: try to find in stripped content
        return _find_line_locator(evidence, "")
    return ""


# ---------------------------------------------------------------------------
# entry_id and excerpt_hash
# ---------------------------------------------------------------------------

def make_entry_id(claim: str, source_file: str) -> str:
    """Deterministic UUID from claim + source (content-based, not random)."""
    h = hashlib.sha256(f"{source_file}::{claim}".encode()).hexdigest()[:12]
    return f"ev-{h}"


def make_excerpt_hash(evidence_text: str) -> str:
    """Hash of the source excerpt for integrity checking."""
    if not evidence_text:
        return ""
    return hashlib.sha256(evidence_text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Ledger builder
# ---------------------------------------------------------------------------

def build_ledger(
    principles: list[dict],
    filepath: str,
    source_hash: str,
    source_metadata: dict | None = None,
    original_text: str = "",
) -> dict:
    """Build an evidence ledger from compiled principles.

    Args:
        principles: list of principle dicts from compilation
        filepath: source file path (for entry_id generation)
        source_hash: SHA-256 of source file
        source_metadata: ingestion metadata (upload_date, title, etc.)
        original_text: original SRT/text with timestamps (before strip_srt)

    Returns:
        Evidence ledger dict with entries and metadata.
    """
    entries = []
    meta = source_metadata or {}

    for p in principles:
        statement = p.get("statement", "")
        evidence = p.get("evidence", "")
        if not statement:
            continue

        # Extract locator from source
        locator = extract_locator(evidence, filepath, original_text)

        # Build entry
        entry = {
            "entry_id": make_entry_id(statement, filepath),
            "claim": statement,
            "source_file": filepath,
            "source_sha256": source_hash,
            "upload_date": meta.get("upload_date", ""),
            "locator": locator,
            "excerpt_hash": make_excerpt_hash(evidence),
            "epistemic_status": p.get("epistemic_status", "speculative"),
            "evidence_text": evidence,
        }

        # Attach refutation if present
        refutation = p.get("refutation")
        if refutation and not refutation.get("_dry_run"):
            entry["refutation"] = {
                "strongest_alternative": refutation.get("strongest_alternative", ""),
                "disconfirming_evidence": refutation.get("disconfirming_evidence", ""),
                "dissent_type": refutation.get("dissent_type", ""),
            }

        entries.append(entry)

    return {
        "version": "1.0",
        "entries": entries,
        "metadata": {
            "source_count": 1,
            "total_entries": len(entries),
            "built_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Ledger lookup (for depth_tracker / drift_detector)
# ---------------------------------------------------------------------------

def lookup_by_claim(ledger: dict, claim: str) -> dict | None:
    """Find ledger entry by claim text (exact match)."""
    for entry in ledger.get("entries", []):
        if entry["claim"] == claim:
            return entry
    return None


def get_evidence_text(ledger: dict, claim: str) -> str:
    """Get evidence_text for a claim, or empty string."""
    entry = lookup_by_claim(ledger, claim)
    return entry["evidence_text"] if entry else ""
