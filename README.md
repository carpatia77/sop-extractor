<h1 align="center">sop-extractor</h1>

<p align="center">
  <strong>Compile any author's books and video courses — one source or a lifetime of them — into a provenance-tracked, time-audited doctrine an LLM can reason from.</strong>
</p>

<p align="center">
  <em>Domain-agnostic: works the same on a single book as on decades of an author's combined books and courses. </em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-203%20passing-38a169?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/PDF%20%E2%80%A2%20EPUB%20%E2%80%A2%20DOCX%20%E2%80%A2%20SRT%2FVTT-supported-d69e2e?style=for-the-badge" alt="Formats supported">
</p>

<p align="center">
  <a href="#-what-it-is">What it is</a> ·
  <a href="#-a-worked-result">Worked result</a> ·
  <a href="#-the-audit-apparatus">Audit apparatus</a> ·
  <a href="#-what-it-generates">What it generates</a> ·
  <a href="#-usage">Usage</a> ·
  <a href="#-why-not-just">Why not just…</a> ·
  <a href="#-credits">Credits</a>
</p>

> **Built on [book-to-skill](https://github.com/virgiliojr94/book-to-skill)** (MIT, by virgiliojr94). This project takes that project's extraction engine — turning a document into an on-demand agent skill — and builds a **knowledge-compilation and auditing layer** on top of it: video-course support, structural determinism scoring, single-source coherence auditing, and a cross-source **Temporal Evolution Audit** that tracks how an author's doctrine changed across decades, with every claim traced back to its source and guarded by deterministic validators.

---

## 🎯 What it is

Most "chat with your documents" tools do retrieval: chunk, embed, find similar
vectors. This does **compilation**: one deep pass extracts an author's actual
decision-logic as **First Principles** (the irreducible truths) and **SOPs**
(the executable procedures), and marks the honestly-probabilistic parts as
**Heuristics** instead of faking determinism.

**It works on a single source** — one book, one course, one folder of docs — and
that alone gives you the provenance-tagged skill plus a same-source coherence
audit. **When you have several works by the same author**, it additionally
**audits how that logic evolved over time** across them. The value starts at one
source and compounds as you add more.

The output is not a summary. It's a decision base with three properties a
summary can't have:

- **Provenance** — every rule ends in a tag like `[src2/2025-01-01, base: src1/2019-01-01]`; if a tag cites a source that doesn't support it, a validator fails the build.
- **Time-awareness** — a `Chronology Gate` forbids an older source from "superseding" a newer one; a `Silence Gate` forbids inferring a rule was dropped just because a later work didn't repeat it.
- **Honesty about uncertainty** — contradictions between sources are **flagged for human judgment**, never silently reconciled. A validator failure means "hallucinated citation → regenerate"; a flagged tension means "real question → a human decides." The two are never conflated.

---

## 🧩 A worked result

The pipeline was built and proven end-to-end on one author's full multi-decade
bibliography — several books and video courses. Measured with
`scripts/extraction_summary.py`: **~21 hours of video** and **~405K tokens** of
source were distilled into per-source skills, then cross-audited into one
reconciled, provenance-tagged doctrine that passed **all traceability gates**.

Two genuine doctrinal reversals surfaced automatically — the kind a human
re-reading a stack of sources over weeks would likely miss:

- **A silent contradiction:** one technical term's meaning was the exact inverse between an earlier book and a later one, with neither acknowledging the change — flagged `contradiction_unmarked` (and honestly caveated as a possible extraction artifact, surfaced rather than asserted).
- **An explicit self-correction:** a later course reverses an earlier stance in the author's own words — verified verbatim against the transcript before being tagged `superseded`.

> The source material used to build and validate this run is third-party
> copyrighted (books and paid courses) and is **not redistributed in this
> repository**. The pipeline is domain-agnostic — point it at material you own
> or at openly-licensed / public-domain sources.

---

## 🛡️ The audit apparatus

This is what the project adds on top of extraction. Each layer is a small,
tested, deterministic script — no LLM self-grading.

| Layer | Script | What it does |
|-------|--------|--------------|
| **Determinism score** | `scripts/determinism_score.py` | Structurally counts SOPs vs. Heuristics per chapter/module (pure regex, reproducible) — measures how procedural a source really is, not the model's opinion of itself. |
| **Coherence audit** | `scripts/validate_coherence_audit.py` | Runs an **isolated** LLM pass over one source's `first_principles.md` + `sops.md` to flag cross-chapter tensions, then validates every flagged citation is real (≥70%). |
| **Temporal evolution audit** | `scripts/validate_evolution_audit.py` | Cross-source lineage matrix guarded by four gates: **Chronology**, **Silence**, **Confidence** (`dropped?` must be low-confidence), and **Claim Verification** (tags trace to source). |
| **Video frame rescue** | `scripts/extract_frames_at_timestamps.py` | For course transcripts, pulls still frames **only** at moments the speaker points at something visual ("look at this") without describing it in words — targeted, never frame-by-frame. Every frame is traceable to its timestamp + transcript context. |
| **Traceability triage** | `scripts/verify_concept_presence.py` | Ranks each First Principle by how much of its wording is grounded in the source transcript, surfacing the least-grounded ones for a human read. A triage aid, not a pass/fail gate. |

The full flow is documented, with a rendered diagram, in
[`docs/PIPELINE_ARCHITECTURE.md`](docs/PIPELINE_ARCHITECTURE.md).

---

## 📦 What it generates

Per source, an on-demand agent skill (the [Agent Skills](https://github.com/agentskills/agentskills) standard — GitHub Copilot CLI, Amp, and other compatible agents):

| File | Purpose |
|------|---------|
| `SKILL.md` | Core First Principles & SOPs + index + Determinism Profile |
| `chapters/ch01-*.md` / `mod01-*.md` | One file per chapter (book) or module (course), loaded on-demand |
| `first_principles.md` | Load-bearing principles, each with its causal "because" and source |
| `sops.md` | Executable procedures, decision tables, thresholds; Heuristics kept separate |
| `glossary.md` | Key terms, alphabetized |
| `frames/` + `frames_manifest.json` | (courses) rescued visual-reference frames |

Across a **Set**, two more: `<author>_evolution.md` (the lineage matrix) and
`<author>_current.md` (the reconciled, provenance-tagged current doctrine).

---

## 🚀 Usage

Extraction is driven by the skill spec in [`SKILL.md`](SKILL.md), which walks
an agent through a Q&A (content type, purpose, name, lineage) before running
the extraction. The deterministic parts — content scanning, scoring,
validation — are plain scripts you can also run directly:

```bash
# Before extracting a PDF: scan it to get a BOOK_TYPE suggestion (text vs.
# technical) instead of guessing from the first chapter — see below
python scripts/preflight_scan.py path/to/source.pdf

# Structural determinism of an extracted source
python scripts/determinism_score.py path/to/your-skill

# Validate a cross-source temporal evolution audit (all four gates)
python scripts/validate_evolution_audit.py --dir path/to/your-set

# Triage how well a course's First Principles trace to its transcript
python scripts/verify_concept_presence.py path/to/your-skill --show-absent

# For a video course: rescue frames at visual-reference gaps (dry-run first)
python scripts/extract_frames_at_timestamps.py path/to/transcript.srt --dry-run

# Run everything discovered in a skill/set directory in one pass
python scripts/validate_all.py path/to/your-skill
```

Supported source formats: PDF, EPUB, DOCX, TXT, Markdown, reStructuredText,
AsciiDoc, HTML, RTF, MOBI/AZW — plus **SRT/VTT** video-course transcripts.

**Before running a Full Conversion**, fill in
[`docs/EXTRACTION_PREFLIGHT_CHECKLIST.md`](docs/EXTRACTION_PREFLIGHT_CHECKLIST.md)
— it walks through the same content-type, depth, destination, and lineage
decisions the skill spec asks about, with the scanner above doing the first
pass for you. Getting the content type wrong (calling a table/diagram-driven
source "text-heavy") is the single most expensive mistake to discover after
a full run has already completed.

**For audiovisual sources (video courses):** the frame-rescue step
(`extract_frames_at_timestamps.py`, [`SKILL.md`](SKILL.md) Step 7.5) needs
**both** the transcript (SRT/VTT) **and** the source video to pull still
frames at the moments the speaker points at something visual without
describing it in words. Keep the transcript file in the same folder as its
corresponding video (one pair per part, for multi-part courses) before
starting extraction — without a transcript alongside the video, this module
has nothing to scan for visual-reference gaps and is skipped entirely.

---

## 🤔 Why not just…

**…dump the whole book into context?** You pay that token bill on **every turn of
every session, forever**. Compilation pays the cost once; each later question
loads only the slice it needs (a resident core plus one chapter). A bigger context
window changes what *fits*, not what's *cheap* — and recall degrades as the window
fills ("lost in the middle").

**…use RAG?** RAG works at query time: "find me chunks near this query." This works
at compile time: extract the author's named frameworks and *when to use each*. RAG
indexes a shelf; this masters a spine. They're complementary — for a library of
dozens of books, use RAG; for one author you want to reason *with*, compile.

**…trust the model's memory of a famous book?** Training-data knowledge is
compressed and averaged across the whole internet's take, and hallucinates specific
quotes and chapter locations. This works from *your* copy — every framework and
chapter number grounded in the text you provided.

---

## 📁 Repository structure

```
sop-extractor/
├── SKILL.md                 # Extraction spec (books, docs, and BOOK_TYPE=transcript courses)
├── scripts/
│   ├── extract.py               # text-extraction entrypoint (book-to-skill engine)
│   ├── determinism_score.py     # structural SOP/Heuristic scoring
│   ├── validate_coherence_audit.py     # single-source coherence validator
│   ├── validate_evolution_audit.py     # cross-source 4-gate temporal validator
│   ├── verify_concept_presence.py      # principle→transcript traceability triage
│   └── extract_frames_at_timestamps.py # targeted video frame rescue
├── tests/                   # pytest suite (203 tests)
└── docs/
    ├── PIPELINE_ARCHITECTURE.md      # end-to-end diagram + how it prevents hallucination
    └── ROADMAP.md                    # technical backlog
```

> No example skills are committed here: the material this pipeline was validated
> on is third-party copyrighted and kept private. Point the scripts at your own
> extracted skills (or openly-licensed sources) to reproduce the workflow.

---

## ⚖️ Copyright & fair use

This tool ships **no third-party book or course content** — it's a compiler you
point at material you own. Extraction runs locally. A generated skill is a
structured, synthesized derivative (framework names, principles, takeaways),
never a reproduction of the source — treat it like personal study notes, and
don't redistribute skills of copyrighted works. No such skills are published in
this repository; the material used to validate the pipeline is kept private.
When in doubt, follow the source's terms.

---

## 🙏 Credits

- **[book-to-skill](https://github.com/virgiliojr94/book-to-skill)** by **virgiliojr94** (MIT) — the extraction engine and the on-demand agent-skill format this project is built on. If you just want to turn a single book into a skill, use that project directly.
- The auditing layer (determinism scoring, coherence audit, temporal evolution audit with the four gates, video-frame rescue, and concept-presence triage) is the addition here.

## License

MIT — applies to the code and specs in this repository, **not** to any book,
course, or document you process with it.
