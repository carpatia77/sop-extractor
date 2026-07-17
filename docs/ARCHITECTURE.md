# Architecture

*Last diagram refresh: 2026-07-17 (Items 11–13 — Blackhat Mode, `sopx`, format
contract, run_report gate, HTML viewer). See [CHANGELOG.md](../CHANGELOG.md)
for the full list of what shipped.*

book-to-skill has two halves: a **deterministic extractor** (Python) and a
**spec-driven generator** (the agent following `SKILL.md`). The extractor turns any
document into clean text + metadata; the agent turns that into a structured skill.
A third, optional layer — the **audit apparatus** — validates what the generator
produced, entirely deterministically, no LLM self-grading.

```
                     ┌──────────────── ENTRYPOINT ────────────────┐
                     │  python scripts/menu.py  (aka `sopx`)        │
                     │  one interactive menu / headless verb        │
                     │  dispatch over every capability below         │
                     └──────────────────────┬───────────────────────┘
                                             ▼
            ┌────────────── PRE-FLIGHT (Python, deterministic) ──────────────┐
            │  scripts/preflight_scan.py                                       │
            │    PDF/txt/md/srt/vtt → BOOK_TYPE recommendation + confidence    │
            │    + re_candidate ("Blackhat Mode" candidacy) + analyst_lens      │
            │  scripts/format_registry.py  ← shared scanner/extractor contract │
            │  --emit-prompt → a ready-to-approve Full Conversion prompt       │
            └────────────────────────────────┬────────────────────────────────┘
                                              ▼
            ┌─────────────────────────── EXTRACTOR (Python, deterministic) ──┐
 documents  │  scripts/extract.py  →  book_to_skill/                          │
 (pdf/epub/ │    ├─ utils.py        CLI parse · multi-source resolve · runner │
 docx/srt/  │    ├─ config.py       supported extensions · paths · deps map   │
  vtt/...)  │    ├─ dependencies.py optional-dep probing · --check report     │
     │      │    └─ parsers/        pdf · epub · docx · html · rtf · calibre  │
     ▼      │                        text · subtitle (srt/vtt)                │
 ───────────│                       (best tool first, stdlib fallback)        │
            │  output → <tempdir>/book_skill_work/                            │
            │    full_text.txt   (all sources merged, source-marked)          │
            │    metadata.json   (pages, words, tokens, chapters, ToC)        │
            └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
            ┌─────────────────────────── GENERATOR (agent, follows SKILL.md) ┐
            │  Step 1.5  content type → BOOK_TYPE (technical|text|transcript) │
            │  Step 2/2.5 extract · cost estimate · confirm                   │
            │  Step 2.6  REPL-style probing for large books (grep/sed, no     │
            │            full re-reads)                                        │
            │  Step 3    analyze structure (title, author, chapters, ToC)     │
            │  Step 4    purpose → DEPTH (reference | study)                   │
            │  Step 7    per-chapter summaries (budget = BOOK_TYPE × DEPTH)    │
            │  Step 7.5  video frame rescue (transcript courses w/ video)      │
            │  Step 8    glossary · first_principles · sops (decision layer)   │
            │  Step 9    SKILL.md core + indexes                               │
            │  Step 9.5  Determinism Score (procedural coverage)               │
            │  Step 9.6  Coherence Audit (cross-chapter contradiction check)   │
            │  Step 9.7  Auto-trigger Set Audit (if lineage registered)        │
            │  Step 9.8  write run_report.json (per-step ran/skipped + reason) │
            │                                                                    │
            │  Optional — Blackhat Mode (Item 11, opt-in, never auto-selected): │
            │  when re_candidate fires, [B] adds <system>_architecture.md —    │
            │  [OBSERVED]/[INFERRED]-sealed reverse-engineering of a           │
            │  demonstrated system, walled off from the faithful core above.   │
            └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                <SKILLS_HOME>/<slug>/  ← chosen per host:
                  ~/.copilot/skills/   GitHub Copilot CLI
                  ~/.agents/skills/    Copilot CLI or Amp (cross-agent)
                  ~/.claude/skills/    other compatible agents
                  .github|.claude|.agents/skills/  project-local
                  SKILL.md               core frameworks + indices + determinism (~4K)
                  chapters/*.md          on-demand, loaded only when asked
                  glossary.md            key terms
                  first_principles.md    load-bearing principles and invariant truths
                  sops.md                executable procedures and decision tables
                  <system>_architecture.md   optional — Blackhat Mode output (Item 11)
                  run_report.json        per-step ran/skipped + reason (Item 13.3)
                                   │
                                   ▼
            ┌───────────────────── AUDIT APPARATUS (deterministic, no LLM) ──┐
            │  scripts/validate_all.py  ← orchestrates all of the below       │
            │    determinism_score.py        structural SOP/Heuristic %      │
            │    verify_concept_presence.py  principle→transcript triage     │
            │    validate_coherence_audit.py    single-source, 4 checks      │
            │    validate_evolution_audit.py    cross-source Set, 4 gates    │
            │    validate_architecture_audit.py Blackhat Mode, 4 gates       │
            │    validate_run_report.py         skipped-step reason gate     │
            │  scripts/render_skill_viewer.py → one self-contained HTML page │
            └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
            ┌───────────────────── SET-LEVEL WORKFLOWS ──────────────────────┐
            │  Temporal Evolution Audit (author Set):                         │
            │  Group multiple skills chronologically via set_manifest.json    │
            │  to track concept evolution across decades.                     │
            └────────────────────────────────────────────────────────────────┘
```

## Design principles

1. **Extract structure, not summaries** — named frameworks, decision rules,
   anti-patterns; never raw passages.
2. **Compile-time over runtime** — pay navigation/structuring once; at query time
   load only the relevant chapter. See [PERFORMANCE.md](PERFORMANCE.md).
3. **On-demand chapters** — `SKILL.md` stays small; chapter files cost tokens only
   when read.
4. **Front-loaded `SKILL.md`** — most important content first (compaction truncates
   from the end).
5. **Graceful degradation** — every format has a stdlib fallback; one bad source is
   skipped, not fatal.

## Key components

| Path | Responsibility |
|------|----------------|
| `scripts/menu.py` | `sopx` — unified CLI, thin dispatcher over every capability below |
| `scripts/extract.py` | thin entrypoint wrapper for the extractor |
| `book_to_skill/utils.py` | CLI parsing, multi-source resolution, chapter/ToC detection, runner |
| `book_to_skill/config.py` | supported extensions, paths, dependency map |
| `book_to_skill/dependencies.py` | optional-dependency probing + `--check` |
| `book_to_skill/parsers/` | one module per format (incl. `subtitle.py` for .srt/.vtt) |
| `scripts/preflight_scan.py` | BOOK_TYPE + Blackhat-candidacy pre-flight scan |
| `scripts/format_registry.py` | single source of truth for scanner↔extractor format coverage |
| `scripts/validate_all.py` | orchestrates the full audit apparatus, one report |
| `scripts/validate_architecture_audit.py` | Blackhat Mode's 4 gates (Item 11) |
| `scripts/validate_run_report.py` | skipped-step-must-have-a-reason gate (Item 13.3) |
| `scripts/render_skill_viewer.py` | renders a skill dir into one static HTML page (Item 13.4) |
| `tools/discovery_tax.py` | measures token cost vs context-dump / discovery loop |
| `tools/validate_skill.py` | checks a generated SKILL.md against host rules (`--lens claude|copilot|amp`) |
| `SKILL.md` | the generator spec (Steps 0–10 + fold-in workflow) |

## Extending

- **New format** → add `parsers/<fmt>.py`, register its extension in `config.py`,
  wire dependency probing in `dependencies.py`, branch in `utils.extract_single_file`.
- **New generation behavior** → edit the relevant Step in `SKILL.md`; keep it lean
  and back the change with evidence (see CONTRIBUTING.md).
