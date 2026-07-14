# Extraction Pre-Flight Checklist

Fill this in — and re-read it — before handing a pre-answered "Full Conversion"
prompt to an executor (human or agent) for a new source. It exists because
`SKILL.md` Steps 1.5, 4, 5, and 5.5 are written as a live Q&A, but in practice
they get pre-answered up front so a run can proceed unattended. Nothing in the
pipeline validates those pre-answers before extraction starts — this checklist
(and the scanner below) is the review step that stands in for that.

This checklist is domain- and subject-agnostic: it applies the same way
regardless of what the source is about.

## Source: ______________________

## 0. Run the automated pre-scan first (PDF, plain-text, or subtitle transcript sources)

```bash
python scripts/preflight_scan.py path/to/source.pdf

# Optionally, get a fully-filled, ready-to-approve Full Conversion prompt:
# BOOK_TYPE from the scan recommendation, DEPTH/name/lineage from sensible
# labeled defaults (override with --depth/--skill-name/--skills-home/--lineage):
python scripts/preflight_scan.py path/to/source.pdf --emit-prompt
```

This samples pages (or, for plain-text/subtitle sources, line-windows spread
across the whole file) and returns a suggested `BOOK_TYPE` with a confidence
level, flagging embedded images and tabular-looking text layout — and, for
video-course transcripts (`.srt`/`.vtt`), whether the material demonstrates a
system (`re_candidate`, see section 0.5 below). It is a **suggestion, not a
verdict** — low/medium confidence or any warning means read the flagged
pages/lines yourself before deciding. Other non-sampled sources (epub/docx)
are not page-sampled; judge them by hand using section 1 below.

**Scanner output — Recommendation:** ______________  **Reason given:** ______________________

The scanner prints both a raw signal (average across sampled windows) and a
final recommendation — the two can differ: in a large, mostly-prose source,
sparse-but-real tables can dilute the average below the auto-suggestion
threshold, so the recommendation is deliberately biased toward `technical`
whenever *any* sampled window shows hard evidence (an image, or a
collapsed-table burst — cells that landed one-per-line instead of aligned
columns, a common PDF-to-text artifact), even if the average alone would
have said `text`. Follow the recommendation, not just the raw signal.

## 0.5 Reverse-engineering candidacy (`re_candidate` / "Blackhat Mode", Item 11)

The scanner also reports whether the source *demonstrates a system* (on-screen
deixis, a repeated named system, outputs shown without their computation). When
`re_candidate` is true it offers two options — **neither is auto-selected**:

- `[A]` faithful doctrine only (normal audit → `SKILL.md`) — **default**.
- `[B]` **Blackhat Mode**: also produce a `<system>_architecture.md` that
  reverse-engineers the backend from the observable frontend, every line sealed
  `[OBSERVED …]` or `[INFERRED ← …]` and checked by
  `scripts/validate_architecture_audit.py`.

- [ ] If I want the reverse-engineering layer, I chose `[B]` **explicitly** —
      it is never assumed, even on a 100%-candidate source. Inferring a
      proprietary backend is speculative by nature.
- [ ] I confirmed (or sharpened) the proposed `analyst_lens`. The scanner
      proposes a generic base (`systems-architect`) plus the source's own
      vocabulary; I refined it to the actual domain (e.g.
      `quantitative-systems-architect`) so the inference reasons as a domain
      expert — **without** that lens ever exempting a claim from citing
      observed evidence (the Grounding Gate is persona-blind).

**Blackhat Mode chosen?** ☐ No (default) ☐ Yes — `analyst_lens`: ______________
**Approved by:** ______________  (recorded in the artifact front matter)

See [`ARCHITECTURE_AUDIT.md`](ARCHITECTURE_AUDIT.md) for the full artifact
grammar and the four gates.

## 1. Content type (`BOOK_TYPE`, Step 1.5)

- [ ] I reviewed the scanner output (or, for non-PDF sources, sampled 3–5
      pages spread across the document by hand — not just the first chapter).
- [ ] I checked whether the source's *core argument* — not incidental
      illustration — is carried by a table, chart, formula, or diagram.
      If yes → `BOOK_TYPE=technical`, regardless of how prose-heavy the
      rest of the source reads. "Text-heavy" describes the source's
      *dominant* content, not its majority page count.
- [ ] If there are load-bearing tables/diagrams, I checked whether they are
      selectable text or rasterized images. If rasterized: they will not
      survive extraction under any `BOOK_TYPE` — note this now, so it's a
      documented, expected gap rather than a surprise found after a full run.

**Chosen `BOOK_TYPE`:** ______________  **Reasoning:** ______________________

## 2. Purpose / depth (`DEPTH`, Step 4)

- [ ] The stated purpose maps to the intended token budget: option 3 only
      → `reference`; anything including option 1, 2, or 4 → `study`.

**Chosen `DEPTH`:** ______________

## 3. Name & destination (Step 5)

- [ ] If `$SKILLS_HOME/<skill_name>/` already exists, I confirmed
      "overwrite" is really intended (not Update/Fold-in, not Rename) —
      a pre-answered "overwrite" in a batch prompt can silently destroy a
      prior extraction.

## 4. Lineage (Step 5.5)

- [ ] Author-name auto-detection only catches same-author lineages. A
      deliberate cross-author grouping (e.g. an originating work feeding
      later authors' extensions in the same field) will never be
      auto-suggested — I decided this explicitly, in writing, rather than
      defaulting to "isolated extraction" by omission.

**Lineage decision:** ______________________

## Sign-off

- [ ] I reviewed all sections above (including the scanner output) before
      handing off the Full Conversion prompt.

Filled in by: ______________  Date: ______________
