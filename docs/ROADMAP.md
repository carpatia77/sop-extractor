# Roadmap — Technical Backlog

Items identified during real extractions/audits, not yet implemented.
Ordered by priority. Each item states *why* (the concrete gap that surfaced
it), not just *what*, so a future implementer knows whether it still matters.

---

## 1. Concept-presence verification mode for transcript First Principles ✅ DONE

**Shipped**: `scripts/verify_concept_presence.py` + `tests/test_verify_concept_presence.py`.
Implemented as a **triage aid, not a pass/fail gate** — the audits proved
token-presence can't cleanly separate fabrication from synthesis glue, so a
hard gate would false-positive on faithful content. The tool: hyphen-splits
before normalizing (fixes the `fast-timeframe`→`fasttimeframe` artifact),
scores each principle by the fraction of its salient terms present in the
`.srt` corpus, ranks lowest-groundedness first, and lists the absent terms
per principle so a human scans the top of the list instead of hand-writing
probes. Default exit 0 (triage); `--gate` exits 2 on flags for CI that wants
to require human sign-off.

**Calibration finding** (why the floor is 0.34, not higher): run against 3
human-audited-faithful courses, exactly one principle across all 75 fell below
0.34. On review it was *faithful in substance* but the single most heavily
paraphrased of the whole set (the extractor restated a plainly-worded source
idea in much more academic vocabulary). That is the intended behavior: surface
the one lowest-groundedness assertion for a closer read, without failing a
build over legitimate paraphrase. A flag means "look here", never "proven
fabrication".

**Known limitation** (documented, acceptable): can't isolate domain terms from
framing glue without POS-tagging/a MP lexicon, so the middle band (0.34–1.0)
still needs a human scan of the absent-term lists. This is triage-grade, not
proof-of-fidelity — which is the honest ceiling for an automated check here.

**History that shaped the design** (kept as context): full-sentence Jaccard
reported only ~24% "verified" on one course's First Principles, all false
negatives (syntheses don't match single sentences). A naive concept-presence
threshold then flagged 13/17 on another course, *also* all false negatives —
from (a) hyphen artifacts, (b) synthesis-glue vocabulary counted as missing,
(c) domain concepts present under different phrasing. Both findings are why the
shipped tool hyphen-splits, ranks-and-lists instead of hard-gating, and sets a
low review floor rather than a high pass bar.

---

## 2. Keep source transcripts private; run traceability locally

**Priority**: standing convention (not a build task)

**Why**: concept-presence and Jaccard traceability need the raw `.srt`/source
text to run. For copyrighted material (books, paid courses), that source
**must not be committed to a public repo** — doing so republishes the
third-party product. Traceability is therefore a **local/private** audit step,
not a repo-reproducible one, for any copyrighted source.

**What**: keep sources (and their extracted skills) in a private working area;
run `verify_concept_presence.py` / `validate_coherence_audit.py` there. Only
commit skills built from material you own outright or from openly-licensed /
public-domain sources. When a source can't be committed, note in the writeup
that traceability was verified privately at audit time.

---

## Done (kept for context)

- ✅ `sequence` tie-breaker for sources sharing a date (commit `6b77776`).
- ✅ `mod*.md` globbing in `determinism_score.py` (commit `7af89f6`).
- ✅ Multi-part video course support + `--part-id` (commit `5cef730`).
- ✅ `BOOK_TYPE=transcript` content type (commit `2392158`).
