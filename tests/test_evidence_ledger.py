#!/usr/bin/env python3
"""Tests for scripts/evidence_ledger.py — provenance per claim.

Tests: SRT parsing, locator extraction, entry_id generation, excerpt_hash,
ledger building, lookup, integration with compile pipeline.
"""
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from evidence_ledger import (
    parse_srt_with_timestamps,
    _find_locator_for_evidence,
    _find_line_locator,
    extract_locator,
    make_entry_id,
    make_excerpt_hash,
    build_ledger,
    lookup_by_claim,
    get_evidence_text,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SRT = """\
1
00:00:01,000 --> 00:00:04,000
Volatility drag compounds against you over time.

2
00:00:05,000 --> 00:00:08,000
Nobody knows the outcome of a single trade.

3
00:00:09,000 --> 00:00:12,000
Higher returns require higher risk.
"""

SAMPLE_PRINCIPLES = [
    {
        "statement": "Volatility drag compounds against you over time",
        "evidence": "Volatility drag compounds against you over time.",
        "epistemic_status": "certain",
    },
    {
        "statement": "Nobody knows the outcome of a single trade",
        "evidence": "Nobody knows the outcome of a single trade.",
        "epistemic_status": "certain",
    },
]


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

class TestParseSrtWithTimestamps:
    def test_parses_cues(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        assert len(cues) == 3

    def test_cue_structure(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        assert cues[0]["index"] == 1
        assert cues[0]["start"] == "00:00:01.000"
        assert cues[0]["end"] == "00:00:04.000"
        assert "volatility drag" in cues[0]["text"].lower()

    def test_empty_srt(self):
        cues = parse_srt_with_timestamps("")
        assert cues == []

    def test_comma_to_dot_in_timestamps(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        assert "," not in cues[0]["start"]
        assert "." in cues[0]["start"]


# ---------------------------------------------------------------------------
# Locator extraction
# ---------------------------------------------------------------------------

class TestFindLocatorForEvidence:
    def test_exact_match(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        locator = _find_locator_for_evidence("Volatility drag compounds", cues)
        assert locator == "00:00:01.000-00:00:04.000"

    def test_partial_match(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        locator = _find_locator_for_evidence("Nobody knows", cues)
        assert locator == "00:00:05.000-00:00:08.000"

    def test_no_match(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        locator = _find_locator_for_evidence("something completely different", cues)
        assert locator == ""

    def test_empty_evidence(self):
        cues = parse_srt_with_timestamps(SAMPLE_SRT)
        locator = _find_locator_for_evidence("", cues)
        assert locator == ""

    def test_empty_cues(self):
        locator = _find_locator_for_evidence("test", [])
        assert locator == ""


class TestFindLineLocator:
    def test_finds_line(self):
        text = "Line one\nLine two\nVolatility drag here\nLine four"
        locator = _find_line_locator("Volatility drag", text)
        assert locator == "line:3"

    def test_no_match(self):
        text = "Line one\nLine two"
        locator = _find_line_locator("not found", text)
        assert locator == ""

    def test_empty_evidence(self):
        locator = _find_line_locator("", "some text")
        assert locator == ""


class TestExtractLocator:
    def test_srt_with_original_text(self):
        locator = extract_locator("Volatility drag", "test.srt", SAMPLE_SRT)
        assert "00:00:01" in locator

    def test_txt_with_original_text(self):
        locator = extract_locator("Volatility drag", "test.txt", "Volatility drag here")
        assert locator == "line:1"

    def test_empty_evidence(self):
        locator = extract_locator("", "test.srt", SAMPLE_SRT)
        assert locator == ""


# ---------------------------------------------------------------------------
# entry_id and excerpt_hash
# ---------------------------------------------------------------------------

class TestEntryId:
    def test_deterministic(self):
        id1 = make_entry_id("claim text", "source.txt")
        id2 = make_entry_id("claim text", "source.txt")
        assert id1 == id2

    def test_different_claims(self):
        id1 = make_entry_id("claim one", "source.txt")
        id2 = make_entry_id("claim two", "source.txt")
        assert id1 != id2

    def test_format(self):
        entry_id = make_entry_id("test", "test.txt")
        assert entry_id.startswith("ev-")
        assert len(entry_id) == 15  # "ev-" + 12 hex chars


class TestExcerptHash:
    def test_deterministic(self):
        h1 = make_excerpt_hash("evidence text")
        h2 = make_excerpt_hash("evidence text")
        assert h1 == h2

    def test_different_texts(self):
        h1 = make_excerpt_hash("text one")
        h2 = make_excerpt_hash("text two")
        assert h1 != h2

    def test_empty(self):
        assert make_excerpt_hash("") == ""


# ---------------------------------------------------------------------------
# Ledger builder
# ---------------------------------------------------------------------------

class TestBuildLedger:
    def test_basic_ledger(self):
        ledger = build_ledger(
            SAMPLE_PRINCIPLES,
            filepath="test.srt",
            source_hash="abc123",
        )
        assert ledger["version"] == "1.0"
        assert len(ledger["entries"]) == 2
        assert ledger["metadata"]["total_entries"] == 2

    def test_entry_fields(self):
        ledger = build_ledger(
            SAMPLE_PRINCIPLES,
            filepath="test.srt",
            source_hash="abc123",
        )
        entry = ledger["entries"][0]
        assert entry["entry_id"].startswith("ev-")
        assert entry["claim"] == "Volatility drag compounds against you over time"
        assert entry["source_sha256"] == "abc123"
        assert entry["epistemic_status"] == "certain"
        assert entry["evidence_text"] == "Volatility drag compounds against you over time."

    def test_locator_from_srt(self):
        ledger = build_ledger(
            SAMPLE_PRINCIPLES,
            filepath="test.srt",
            source_hash="abc123",
            original_text=SAMPLE_SRT,
        )
        entry = ledger["entries"][0]
        assert "00:00:01" in entry["locator"]

    def test_upload_date_from_metadata(self):
        metadata = {"upload_date": "2024-05-15", "title": "Test Video"}
        ledger = build_ledger(
            SAMPLE_PRINCIPLES,
            filepath="test.srt",
            source_hash="abc123",
            source_metadata=metadata,
        )
        assert ledger["entries"][0]["upload_date"] == "2024-05-15"

    def test_refutation_attached(self):
        principles = [
            {
                "statement": "Test claim",
                "evidence": "Test evidence",
                "epistemic_status": "certain",
                "refutation": {
                    "strongest_alternative": "Alternative view",
                    "disconfirming_evidence": "Would be false if X",
                    "dissent_type": "qualifies",
                },
            }
        ]
        ledger = build_ledger(principles, "test.txt", "hash")
        entry = ledger["entries"][0]
        assert entry["refutation"]["strongest_alternative"] == "Alternative view"
        assert entry["refutation"]["dissent_type"] == "qualifies"

    def test_refutation_dry_run_not_attached(self):
        principles = [
            {
                "statement": "Test claim",
                "evidence": "Test evidence",
                "refutation": {"_dry_run": True, "_prompt": "..."},
            }
        ]
        ledger = build_ledger(principles, "test.txt", "hash")
        assert "refutation" not in ledger["entries"][0]

    def test_empty_principles(self):
        ledger = build_ledger([], "test.txt", "hash")
        assert ledger["entries"] == []
        assert ledger["metadata"]["total_entries"] == 0

    def test_principle_without_evidence(self):
        principles = [{"statement": "Claim only", "epistemic_status": "probable"}]
        ledger = build_ledger(principles, "test.txt", "hash")
        entry = ledger["entries"][0]
        assert entry["evidence_text"] == ""
        assert entry["locator"] == ""
        assert entry["excerpt_hash"] == ""

    def test_principle_without_statement_skipped(self):
        principles = [{"evidence": "Evidence only"}]
        ledger = build_ledger(principles, "test.txt", "hash")
        assert len(ledger["entries"]) == 0


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_lookup_found(self):
        ledger = build_ledger(SAMPLE_PRINCIPLES, "test.txt", "hash")
        entry = lookup_by_claim(ledger, "Volatility drag compounds against you over time")
        assert entry is not None
        assert entry["entry_id"].startswith("ev-")

    def test_lookup_not_found(self):
        ledger = build_ledger(SAMPLE_PRINCIPLES, "test.txt", "hash")
        entry = lookup_by_claim(ledger, "Nonexistent claim")
        assert entry is None

    def test_get_evidence_text(self):
        ledger = build_ledger(SAMPLE_PRINCIPLES, "test.txt", "hash")
        text = get_evidence_text(ledger, "Volatility drag compounds against you over time")
        assert "volatility drag" in text.lower()

    def test_get_evidence_text_not_found(self):
        ledger = build_ledger(SAMPLE_PRINCIPLES, "test.txt", "hash")
        text = get_evidence_text(ledger, "Nonexistent")
        assert text == ""
