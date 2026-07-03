import os
import tempfile
import pytest
from scripts.verify_concept_presence import (
    salient_terms,
    score_principle,
    build_corpus,
    extract_principles,
    verify_source,
    REVIEW_FLOOR,
)


def test_salient_terms_splits_hyphens():
    # 'fast-timeframe' must become two matchable tokens, not 'fasttimeframe'
    terms = salient_terms("fast-timeframe and slow-timeframe theses")
    assert "fast" in terms and "timeframe" in terms
    assert "fasttimeframe" not in terms

def test_salient_terms_drops_stopwords_and_dedupes():
    terms = salient_terms("the market is the market")
    assert "the" not in terms and "is" not in terms
    assert terms.count("market") == 1  # de-duplicated

def test_score_principle_full_presence():
    r = score_principle("value area point of control", "the value area is built from the point of control")
    assert r["score"] == 1.0
    assert r["absent"] == []

def test_score_principle_partial_and_absent_list():
    r = score_principle("tempo exhaustion elliott waves", "tempo signals exhaustion in the auction")
    assert 0 < r["score"] < 1
    assert "elliott" in r["absent"] and "waves" in r["absent"]
    assert "tempo" in r["present"]

def test_score_principle_fabrication_scores_low():
    # A claim whose domain terms are wholly absent from the source
    r = score_principle("fibonacci retracement golden ratio harmonic", "the author talks about auctions and value")
    assert r["score"] == 0.0

def test_score_principle_faithful_synthesis_above_floor_despite_framing():
    # A faithful principle can still leave framing words ('event','level')
    # unmatched — it lands at 0.5 here (markets+random present, event+level
    # not), which is above REVIEW_FLOOR (0.34) so it is NOT flagged. This is
    # exactly why the floor is low: faithful syntheses carry framing glue.
    claim = "markets are random at the event level"
    corpus = "here's one to write down markets are random and that frustrates people"
    r = score_principle(claim, corpus)
    assert r["score"] == 0.5
    assert r["score"] >= REVIEW_FLOOR  # not flagged

def test_build_corpus_strips_srt_structure():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "transcripts"))
        with open(os.path.join(d, "transcripts", "a.srt"), "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\nthe auction rotates\n\n")
        corpus = build_corpus(d)
        assert "auction" in corpus and "rotates" in corpus
        assert "-->" not in corpus
        assert "00:00:01" not in corpus

def test_build_corpus_hyphen_split():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "transcripts"))
        with open(os.path.join(d, "transcripts", "a.srt"), "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\nsemi-permeable membrane\n\n")
        corpus = build_corpus(d)
        # 'semi-permeable' in source must match 'semi permeable' claim terms
        r = score_principle("semi-permeable membrane", corpus)
        assert r["score"] == 1.0

def test_extract_principles_pulls_bold_assertion():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "first_principles.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("## Section\n- **The market is an auction** — because reasons. (Mod 1)\n")
        assert extract_principles(p) == ["The market is an auction"]

def test_verify_source_flags_low_groundedness_and_sorts():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "transcripts"))
        with open(os.path.join(d, "transcripts", "a.srt"), "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\nthe auction rotates around value and the point of control\n\n")
        with open(os.path.join(d, "first_principles.md"), "w", encoding="utf-8") as f:
            f.write(
                "- **The auction rotates around value** — grounded. (Mod 1)\n"
                "- **Fibonacci golden ratio harmonic elliott** — fabricated. (Mod 2)\n"
            )
        out = verify_source(d)
        assert out["n_principles"] == 2
        # lowest score first
        assert out["results"][0]["score"] < out["results"][1]["score"]
        # the fabricated one is review-flagged, the grounded one is not
        flagged_claims = [r["claim"] for r in out["review_flags"]]
        assert any("Fibonacci" in c for c in flagged_claims)
        assert not any("auction rotates" in c for c in flagged_claims)

def test_verify_source_missing_transcripts_errors():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "first_principles.md"), "w", encoding="utf-8") as f:
            f.write("- **X** — y.\n")
        out = verify_source(d)
        assert "error" in out

def test_review_floor_is_calibrated_constant():
    # Guard against accidental drift of the calibrated threshold
    assert 0.30 <= REVIEW_FLOOR <= 0.40
