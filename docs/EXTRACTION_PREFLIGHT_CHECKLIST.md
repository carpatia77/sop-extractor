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

## 0. Run the automated pre-scan first (PDF sources)

```bash
python scripts/preflight_scan.py path/to/source.pdf
```

This samples pages spread across the whole document (not just the front) and
returns a suggested `BOOK_TYPE` with a confidence level, flagging embedded
images and tabular-looking text layout. It is a **suggestion, not a verdict**
— low/medium confidence or any warning means read the flagged pages yourself
before deciding. Non-PDF sources (epub/docx/txt/md) are not page-sampled;
judge them by hand using section 1 below.

**Scanner output:** BOOK_TYPE suggestion: ______________  Confidence: ______________

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
