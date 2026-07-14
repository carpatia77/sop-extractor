#!/usr/bin/env python3
"""Concept-presence triage for transcript First Principles.

Why this exists: full-sentence Jaccard (validate_coherence_audit.verify_claim)
under-reports fidelity for *synthesized* First Principles — a compressed
assertion spanning minutes of spoken speech never Jaccard-matches any single
transcript sentence, so it flags faithful syntheses as "unverified" (see
docs/ROADMAP.md item 1, and the course-extraction audits).

What this does instead: for each First Principle, it isolates the salient
terms of the assertion and reports which of them are ABSENT from the source
corpus. It is deliberately a **triage aid, not a pass/fail gate**: token
presence alone cannot cleanly separate a genuine fabrication (a domain term
absent from the source) from a faithful synthesis whose framing/glue words
("symmetrically", "mutually", "culmination") are naturally absent. The audits
proved a naive threshold produces false positives. So this tool automates the
tedious part — finding the absent terms — and leaves the judgment (is this
absence benign glue, or a real fabricated claim?) to a human, hard-flagging
only principles whose salient terms are *mostly* absent (the fabrication
signature, calibrated against three human-audited-faithful courses).
"""

import argparse
import glob
import os
import re
import sys

try:
    from scripts.validate_coherence_audit import STOPWORDS
    from scripts.domain_synonyms import load_domain_synonyms, normalize_text
except ImportError:
    from validate_coherence_audit import STOPWORDS
    from domain_synonyms import load_domain_synonyms, normalize_text

# Calibrated against 3 human-audited-faithful course extractions.
# A score below this means
# the majority of an assertion's salient terms are absent from the source.
# IMPORTANT: a flag is "look here first", NOT "fabrication". When this floor
# was set, exactly one principle across all 75 fell below it
# (one course's most-paraphrased principle, at 20%); on human review it was
# *faithful in substance* but the single most heavily paraphrased of the set
# — the source stated the idea plainly and the extractor restated it in much
# more academic vocabulary. That is exactly what this floor should surface:
# the lowest-groundedness principle worth a closer read, not a build-breaking
# failure.
REVIEW_FLOOR = 0.34


def salient_terms(claim: str) -> list:
    """Salient terms of an assertion: hyphen/slash split FIRST (so
    'fast-timeframe' → 'fast','timeframe' instead of the un-matchable
    'fasttimeframe'), then lowercase, strip punctuation, drop stopwords.
    Order-preserving, de-duplicated."""
    s = re.sub(r'[-/]', ' ', claim.lower())
    s = re.sub(r'[^\w\s]', '', s)
    seen = set()
    terms = []
    for tok in s.split():
        if tok in STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
    return terms


def build_corpus(source_dir: str) -> str:
    """Concatenates all .srt transcript text (dropping index lines and
    timestamp arrows) into one normalized lowercase string."""
    corpus = []
    for srt in sorted(glob.glob(os.path.join(source_dir, "transcripts", "*.srt"))):
        with open(srt, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.isdigit() or "-->" in line:
                    continue
                corpus.append(line)
    text = " ".join(corpus).lower()
    # Hyphen-split the corpus too, so 'semi-permeable' in the source matches
    # 'semi permeable' (or vice-versa) after the same split on the claim side.
    return re.sub(r'[-/]', ' ', text)


def score_principle(claim: str, corpus: str, synonym_map: dict = None) -> dict:
    """Fraction of an assertion's salient terms present in the corpus, plus
    the list of absent terms for human triage."""
    if synonym_map:
        claim = normalize_text(claim, synonym_map)
        
    terms = salient_terms(claim)
    if not terms:
        return {"score": 1.0, "present": [], "absent": [], "n_terms": 0}
    present = [t for t in terms if re.search(r'\b' + re.escape(t) + r'\b', corpus)]
    absent = [t for t in terms if t not in present]
    return {
        "score": len(present) / len(terms),
        "present": present,
        "absent": absent,
        "n_terms": len(terms),
    }


def extract_principles(first_principles_path: str) -> list:
    """Pulls the bolded assertion from each First Principle bullet."""
    with open(first_principles_path, encoding="utf-8") as f:
        text = f.read()
    return re.findall(r'^- \*\*(.+?)\*\*', text, re.MULTILINE)


def verify_source(source_dir: str, floor: float = REVIEW_FLOOR, synonym_map: dict = None) -> dict:
    fp_path = os.path.join(source_dir, "first_principles.md")
    if not os.path.exists(fp_path):
        return {"error": f"no first_principles.md in {source_dir}"}
    if not glob.glob(os.path.join(source_dir, "transcripts", "*.srt")):
        return {"error": f"no transcripts/*.srt in {source_dir} — cannot verify"}

    corpus = build_corpus(source_dir)
    if synonym_map:
        corpus = normalize_text(corpus, synonym_map)
        
    principles = extract_principles(fp_path)
    results = []
    for p in principles:
        r = score_principle(p, corpus, synonym_map)
        r["claim"] = p
        r["review_flag"] = r["score"] < floor
        results.append(r)
    # Lowest groundedness first — the human scans from the top.
    results.sort(key=lambda r: r["score"])
    return {
        "source": os.path.basename(source_dir.rstrip("/")),
        "n_principles": len(principles),
        "review_flags": [r for r in results if r["review_flag"]],
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Concept-presence triage for transcript First Principles (not a hard gate)."
    )
    parser.add_argument("source_dir", help="A skill folder containing first_principles.md and transcripts/*.srt")
    parser.add_argument("--floor", type=float, default=REVIEW_FLOOR,
                        help=f"Flag principles scoring below this for a closer read (default {REVIEW_FLOOR}, calibrated on 3 faithful courses)")
    parser.add_argument("--show-absent", action="store_true",
                        help="List absent salient terms per principle (triage detail)")
    parser.add_argument("--gate", action="store_true",
                        help="Exit 2 if any principle is review-flagged (for CI that wants to require human sign-off). Default exits 0 — this is a triage aid, not a pass/fail gate.")
    parser.add_argument("--domain", default=None,
                        help="Domain ID to load synonyms for (e.g. market-structure)")
    args = parser.parse_args()

    synonym_map = load_domain_synonyms(args.domain) if args.domain else None
    out = verify_source(args.source_dir, floor=args.floor, synonym_map=synonym_map)
    if "error" in out:
        print(f"Error: {out['error']}")
        sys.exit(1)

    print(f"Concept-presence triage — {out['source']} ({out['n_principles']} principles, lowest groundedness first)")
    print(f"Review-flagged (score < {args.floor} — look here first, NOT proven fabrication): {len(out['review_flags'])}\n")

    for r in out["results"]:
        mark = "🔎" if r["review_flag"] else "  "
        print(f"{mark} {r['score']*100:5.0f}%  {r['claim'][:72]}")
        if args.show_absent and r["absent"]:
            print(f"          absent: {r['absent']}")

    print("\nReminder: a flag means 'the assertion's wording is mostly not in the "
          "source' — usually heavy paraphrase (benign), occasionally a fabricated "
          "claim (real). Inspect the absent terms to tell which; the tool does not "
          "decide that for you.")

    if args.gate and out["review_flags"]:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
