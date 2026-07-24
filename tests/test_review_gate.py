#!/usr/bin/env python3
"""Tests for scripts/review_gate.py — mandatory sample review gate (§2.5)."""
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from review_gate import (
    compute_sample_indices,
    present_for_review,
    record_review,
    record_not_reviewed,
    should_abort_batch,
)


# ---------------------------------------------------------------------------
# Sample index selection — risk-weighted
# ---------------------------------------------------------------------------

class TestComputeSampleIndices:
    def test_always_includes_first_item(self):
        """First item is always sampled (calibration baseline)."""
        indices = compute_sample_indices(10, sample_rate=0.10)
        assert 0 in indices

    def test_default_rate_10_percent(self):
        """Default 10% rate on 20 items = 2 samples."""
        indices = compute_sample_indices(20, sample_rate=0.10)
        assert len(indices) == 2  # max(1, ceil(20*0.10)) = 2

    def test_single_item(self):
        """Single item always sampled."""
        indices = compute_sample_indices(1, sample_rate=0.10)
        assert indices == [0]

    def test_empty_batch(self):
        """Empty batch returns nothing."""
        indices = compute_sample_indices(0, sample_rate=0.10)
        assert indices == []

    def test_zero_rate_returns_empty(self):
        """Explicit zero rate disables sampling."""
        indices = compute_sample_indices(10, sample_rate=0)
        assert indices == []

    def test_rate_one_samples_all(self):
        """100% rate samples everything."""
        indices = compute_sample_indices(10, sample_rate=1.0)
        assert indices == list(range(10))

    def test_low_confidence_prioritized(self):
        """Low confidence items are sampled before high confidence."""
        confidence = [0.9, 0.3, 0.8, 0.2, 0.95]
        # 5*0.5=3 samples: index 0 + two low-confidence
        indices = compute_sample_indices(5, sample_rate=0.5, confidence_scores=confidence)
        assert 0 in indices  # always first
        assert 1 in indices  # confidence 0.3
        assert 3 in indices  # confidence 0.2

    def test_re_candidate_prioritized(self):
        """re_candidate items are sampled."""
        re_cands = [False, True, False, True, False]
        # 5*0.5=3 samples: index 0 + two re_candidates
        indices = compute_sample_indices(5, sample_rate=0.5, re_candidates=re_cands)
        assert 0 in indices
        assert 1 in indices
        assert 3 in indices

    def test_longest_sources_fill_remaining(self):
        """Longest sources fill remaining budget."""
        lengths = [100, 5000, 200, 8000, 300]
        indices = compute_sample_indices(5, sample_rate=0.4, source_lengths=lengths)
        # First item (0) + longest (3, then 1) fills budget
        assert 0 in indices
        assert 3 in indices  # 8000 chars

    def test_no_duplicates(self):
        """No index appears twice even with overlapping criteria."""
        confidence = [0.1, 0.1, 0.1, 0.1, 0.1]
        re_cands = [True, True, True, True, True]
        lengths = [1000, 2000, 3000, 4000, 5000]
        indices = compute_sample_indices(
            5, sample_rate=0.6,
            confidence_scores=confidence,
            re_candidates=re_cands,
            source_lengths=lengths,
        )
        assert len(indices) == len(set(indices))

    def test_sorted_output(self):
        """Output is always sorted."""
        indices = compute_sample_indices(20, sample_rate=0.3)
        assert indices == sorted(indices)

    def test_never_exceeds_batch_size(self):
        """Sample count never exceeds batch size."""
        indices = compute_sample_indices(3, sample_rate=0.5)
        assert len(indices) <= 3

    def test_all_indices_valid(self):
        """All indices are within [0, n_items)."""
        indices = compute_sample_indices(10, sample_rate=0.25)
        assert all(0 <= i < 10 for i in indices)


# ---------------------------------------------------------------------------
# Present for review
# ---------------------------------------------------------------------------

class TestPresentForReview:
    def test_includes_filename(self):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        text = present_for_review(0, 5, "video.txt", sections, "source content")
        assert "video.txt" in text
        assert "1/5" in text

    def test_includes_principles(self):
        sections = {
            "sops": [],
            "principles": [{"statement": "Rule 1", "epistemic_status": "certain", "evidence": "because"}],
            "concepts": [],
            "references": [],
        }
        text = present_for_review(0, 1, "v.txt", sections, "source")
        assert "Rule 1" in text
        assert "certain" in text

    def test_includes_source_excerpt(self):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        text = present_for_review(0, 1, "v.txt", sections, "long source text here")
        assert "long source text here" in text

    def test_truncates_long_source(self):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        long = "x" * 1000
        text = present_for_review(0, 1, "v.txt", sections, long, max_excerpt=100)
        assert "x" * 100 in text
        assert "..." in text

    def test_shows_sops(self):
        sections = {
            "sops": [{"name": "My SOP", "steps": ["step 1", "step 2"], "when_to_use": "always"}],
            "principles": [],
            "concepts": [],
            "references": [],
        }
        text = present_for_review(0, 1, "v.txt", sections, "source")
        assert "My SOP" in text
        assert "step 1" in text

    def test_shows_grounding_score(self):
        sections = {
            "sops": [],
            "principles": [{"statement": "Rule", "epistemic_status": "certain",
                            "_grounding_score": 0.85}],
            "concepts": [],
            "references": [],
        }
        text = present_for_review(0, 1, "v.txt", sections, "source")
        assert "85%" in text


# ---------------------------------------------------------------------------
# Review recording
# ---------------------------------------------------------------------------

class TestReviewRecording:
    def test_record_review_appends(self):
        log = []
        record_review(log, 0, "a.txt", {
            "verdict": "approve",
            "timestamp": "2026-01-01T00:00:00Z",
            "editor": "tester",
        })
        assert len(log) == 1
        assert log[0]["verdict"] == "approve"
        assert log[0]["sampled"] is True

    def test_record_not_reviewed(self):
        log = []
        record_not_reviewed(log, 3, "b.txt")
        assert len(log) == 1
        assert log[0]["sampled"] is False
        assert log[0]["index"] == 3


# ---------------------------------------------------------------------------
# Abort logic
# ---------------------------------------------------------------------------

class TestShouldAbortBatch:
    def test_no_rejects_no_abort(self):
        log = [{"verdict": "approve"}, {"verdict": "approve"}]
        assert not should_abort_batch(log, continue_on_reject=False)

    def test_reject_aborts_by_default(self):
        log = [{"verdict": "approve"}, {"verdict": "reject"}]
        assert should_abort_batch(log, continue_on_reject=False)

    def test_reject_no_abort_with_flag(self):
        log = [{"verdict": "approve"}, {"verdict": "reject"}]
        assert not should_abort_batch(log, continue_on_reject=True)

    def test_edit_no_abort(self):
        log = [{"verdict": "edit"}, {"verdict": "approve"}]
        assert not should_abort_batch(log, continue_on_reject=False)

    def test_empty_log_no_abort(self):
        assert not should_abort_batch([], continue_on_reject=False)
