# Changelog

All notable changes to **sop-extractor** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-07-24

### Added
- **Ingestion pipeline (`sopx ingest`).** Download/transcribe video from URL
  or local file → SRT + full_text.txt + metadata.json.
  - `sopx/` package: Config Manager, Cache Manager, Ingest Pipeline.
  - `sopx/ingest/adapters.py`: YtDlpAdapter, FFmpegAdapter, WhisperAdapter.
  - `sopx/ingest/pipeline.py`: Orchestration layer with cache dedup.
  - `scripts/ingest.py`: CLI entry point for `sopx ingest`.
  - Dependencies: `yt-dlp`, `ffmpeg` (system), `faster-whisper` (pip).
  - `sopx ingest --check`: verify all dependencies are installed.
  - `sopx ingest --status`: show cache of processed videos.
  - Hash-based cache prevents reprocessing of already-ingested sources.
  - PT-BR error messages throughout.
- **Hardware-adaptive transcription.** Hardware detection (CPU/RAM/GPU tier)
  drives batch size, beam size, and audio-segmentation settings; int8
  quantization + batched inference for roughly 3x faster transcription;
  long videos are segmented for safer processing. Real-time `tqdm` progress
  per pipeline stage, a pre-flight video summary, and a completion summary
  with a next-step prompt.
- **Google Colab GPU integration.** `sopx ingest <url> --gpu` generates a
  ready-to-run Colab notebook (GPU transcription for users without local
  GPU access); smart routing (`sopx/ingest/router.py`) recommends local vs.
  Colab based on detected hardware and input type (single video / multiple
  URLs / playlist); playlist batch ingestion with frame-extraction
  integration; `sopx ingest --import-zip/--import-dir` imports Colab output
  back into the local pipeline and cache.
- **Provenance loop closure.** `sopx set-build` auto-populates
  `set_manifest.json` from ingestion metadata (`upload_date`,
  `canonical_id`) as a labeled, confirmable proposal — never silently
  authoritative, never fabricated when a date is unavailable (`needs_date`
  flag + fail-fast via the real `validate_manifest.py`). `SOURCE_DATE` is
  now auto-detected in `preflight_scan.py`'s extraction prompt when
  ingestion metadata sits alongside the source. Idempotent merge preserves
  human date corrections on re-run. Design rationale in
  `docs/PROVENANCE_LOOP_PLAN.md`.

### Fixed
- **Critical regressions found reviewing the ingestion work:** the stage
  cache now uses a completion sentinel + atomic writes (a crash mid-write
  could no longer be mistaken for a finished stage), `config.py` deep-copies
  its defaults (a caller mutating its config could no longer poison every
  other caller in the process), and the pipeline's stage-cache check/wiring
  was corrected (it was silently a permanent cache miss, re-downloading and
  re-transcribing on every run).
- **CI governance:** the push trigger targeted a `master` branch that
  doesn't exist (the default is `main`, so pushes to `main` never ran CI);
  `sopx/` was missing from the lint scope; the test matrix now installs the
  `[ingest]` extra and system `ffmpeg` so ingestion tests actually exercise
  real dependencies instead of only mocks.
- **Colab notebook generation bugs**, each found by actually running a
  generated notebook end-to-end: `BatchedInferencePipeline`'s `batch_size`
  parameter passed to the wrong call, a Python syntax error and mixed
  f-string/`.format()` usage in generated cells, download errors hidden by
  a redirected stderr, and a ZIP archive created before its source files
  were fully written. Documented as ground truth in
  `docs/COLAB_SCRIPT_INCIDENTS.md`.
- `word_count` cache accounting, `--no-cache` timestamp handling, and
  yt-dlp anti-throttling measures for playlist ingestion.
- Several edge cases found via targeted stress-testing of the ingestion
  module (`tests/test_stress_ingestion.py`).
- **`build_set_manifest.py` hardening**, found in review: the manifest
  validator now calls the real `validate_manifest.py` instead of a
  reimplementation that had already silently diverged (accepting an empty
  date the real validator rejects); a bare-script invocation
  (`python scripts/build_set_manifest.py ...`, the same path `menu.py`'s
  subprocess dispatch uses) no longer crashes with `ModuleNotFoundError`
  when the package isn't `pip install`ed; `--skills-root` no longer crashes
  when the skill directory and the output directory are unrelated trees;
  `--dry-run` no longer risks writing the real manifest file as a side
  effect of validation.

### Changed
- Local file ingestion now reuses the stage cache for audio extraction
  (was re-extracting on every run, unlike the URL-download path).

## [2.1.1] - 2026-07-22

### Added
- **PT-BR README (`README-PTBR.md`).** Simplified Portuguese version with
  3-command quick-start, ASCII pipeline diagram, supported formats table,
  and generated-skill file reference. Language badge added to EN README
  linking both versions.

## [2.1.0] - 2026-07-22

### Changed
- **PT-BR translation of `preflight_scan.py`.** All user-facing strings
  translated to Portuguese — warnings, recommendation reasons, prompt draft,
  batch report. UX rework: aligned columns, confidence icons (●/◐/○),
  `→` arrow on RECOMENDAÇÃO, condensed warnings, renamed "Linhas curtas"
  → "Tabelas colapsadas" for clarity. Fixed "não varredura completa"
  → "varredura parcial".
- **Repo organizational cleanup.** Published 5 previously-orphaned docs
  (`ARCHITECTURE_AUDIT.md`, `INFRA_MATURITY_PLAN.md`, `OPERATING_CONVENTIONS.md`,
  `PIPELINE_ARCHITECTURE.md`, `EXTRACTION_PREFLIGHT_CHECKLIST.md`) to the
  `mkdocs.yml` nav so they're actually browsable in the docs site. Retired
  `docs/ROADMAP.md` (superseded by `INFRA_MATURITY_PLAN.md`), folding its still
  -relevant "keep source transcripts private" convention into
  `OPERATING_CONVENTIONS.md` item 6. Added `tests/conftest.py` to remove the
  `sys.path` boilerplate duplicated across 7 test files. Refactored
  `scripts/extraction_summary.py` into pure, testable functions with new
  coverage in `tests/test_extraction_summary.py` — no CLI behavior change.

### Added
- **`sopx` console-script entry point.** `pip install -e .` now puts `sopx`
  on your PATH — `scripts/` is packaged into the wheel alongside
  `book_to_skill`, and `sopx = "scripts.menu:main"` is registered in
  `pyproject.toml`'s `[project.scripts]`. Previously `sopx` was only a name
  used in docs; the actual command was `python scripts/menu.py`, which still
  works identically for anyone who hasn't (or can't) `pip install`. Verified
  with a real editable install, a real non-editable wheel install, and
  running `sopx scan`/`sopx validate`/`sopx view` from outside the repo.
- **`scripts/merge_architecture_audit.py` — consolidates multi-part Blackhat
  Mode artifacts (Item 14.1).** Processing a course in separate parts produces
  one `<system>_architecture.md` per part, each numbering its `O`/`I` ids from
  scratch. This script merges N of them into one artifact with continuous
  numbering, rewritten `INFERRED` citations, pooled (not interleaved) sections,
  and preserved per-source prose — then re-validates the result against the
  same Seal/Grounding/Intent gates `validate_architecture_audit.py` enforces.
  Automates exactly the manual renumber-and-consolidate labor a real two-part
  ASG course extraction required this week. Wired into `sopx` as `merge-arch`.
- **Batch dispatch for multi-part courses in `scripts/preflight_scan.py`
  (Item 14.2).** `preflight_scan.py part1.srt part2.srt --emit-prompt` now
  scans every part and emits one Full Conversion prompt covering the whole
  course (`PART_ID=part1..partN`, matching `SKILL.md`'s existing multi-part
  convention), instead of requiring one manual run per part and hand-stitched
  prompts. Warns if parts disagree on `BOOK_TYPE`; points at
  `merge_architecture_audit.py` as the next step when any part is a Blackhat
  Mode candidate. Single-path invocation is unchanged (no regression).
- Registered **Item 14** in `docs/INFRA_MATURITY_PLAN.md`.

## [2.0.0] - 2026-07-19

### Changed
- **License change:** Switched from MIT to Apache-2.0 for the sop-extractor codebase.
- **Project renamed:** `book-to-skill` → `sop-extractor` (the upstream MIT code remains in `book_to_skill/` as a vendored dependency).
- **Third-party attribution:** Added `NOTICES.md` documenting the MIT license for the upstream `book-to-skill` code by virgiliojr94.

### Added
- `NOTICES.md` — Third-party license documentation for vendored `book_to_skill/` package.

## [1.3.0] - 2026-07-17

### Added
- **Architecture Reverse-Engineering Audit — "Blackhat Mode" (Item 11).** An
  opt-in fourth audit layer that reconstructs a demonstrated system's backend
  from its observable frontend, kept walled off from the anti-fabrication core:
  - `scripts/validate_architecture_audit.py` — deterministic, no-LLM validator
    for a `<system>_architecture.md` artifact, with four gates: **Seal** (every
    bulleted claim carries exactly one `[OBSERVED …]`/`[INFERRED …]` seal),
    **Grounding** (every inference cites ≥1 real observed id; persona-blind, so
    an expert lens never licenses uncited inference), **Non-Contamination** (no
    `[INFERRED …]` seal in `SKILL.md`/`first_principles.md`/`sops.md`), and
    **Intent** (front matter records `intent: reverse-engineering`, an approver,
    and the confirmed `analyst_lens`).
  - `scripts/preflight_scan.py` now detects reverse-engineering **candidacy**
    (`re_candidate`) from on-screen/UI deixis, a repeated named system, and
    outputs-shown-without-computation, and proposes an evidence-derived
    `analyst_lens` — surfacing an `[A]` faithful / `[B]` Blackhat Mode choice
    (`[A]` default; RE mode never auto-selected).
  - `docs/ARCHITECTURE_AUDIT.md` documents the artifact grammar and gates.
- **Subtitle transcript (`.srt`/`.vtt`) support, scanner and extractor.**
  Previously `.srt`/`.vtt` fell through the pre-flight scanner to the generic
  low-confidence default (no real signal, no reverse-engineering candidacy
  check) and were rejected outright by the extraction pipeline. Both are now
  fixed: `preflight_scan.py` strips cue indices/timestamps/WEBVTT headers down
  to spoken words before sampling and correctly reports `BOOK_TYPE=transcript`;
  `book_to_skill/parsers/subtitle.py` gives the extractor matching support
  (`SUBTITLE_EXTENSIONS` in `config.py`, a dispatch branch in
  `extract_single_file`) so a Full Conversion no longer fails on the same file
  the scanner just approved.
- **`scripts/menu.py` — unified `sopx`-style CLI (Item 12 / Item 13.1).** A
  thin dispatcher over every existing deterministic script: scan, validate,
  coherence/evolution/Blackhat audits, determinism score, the new HTML viewer,
  and the run/summary log — one interactive menu (`python scripts/menu.py`) or
  headless (`python scripts/menu.py scan path.pdf`, byte-identical to the
  manual command). Greys out any capability whose backing script is missing,
  never lists a dead option as if it worked.
- **`scripts/render_skill_viewer.py` — static HTML skill viewer (Item 13.4).**
  Renders a skill directory (SKILL.md, chapters/, `<system>_architecture.md`,
  determinism score) into one self-contained HTML page — no server, no
  dependency — with provenance tags and `[OBSERVED]`/`[INFERRED]` seals
  rendered as distinct colored badges. Wired into `sopx view <skill_dir>`.
- **`scripts/format_registry.py` + format-parity test (Item 13.2).** A single
  source of truth for which formats the pre-flight scanner has real signal
  for, checked against the extractor's actually-supported formats. Prevents
  a repeat of the `.srt`/`.vtt` incident (scanner recommended a BOOK_TYPE for
  a format the extraction pipeline rejected outright) by failing the build if
  the two ever drift apart again.
- **`scripts/validate_run_report.py` + `run_report.json` convention (Item
  13.3).** `SKILL.md` now asks the executor to record, per step, whether it
  ran or was skipped and why. The validator (wired into `validate_all.py` as
  an informational check) doesn't judge whether a skip reason is *true* — it
  only enforces that one was recorded, turning a silent skip into something a
  human reviewer can catch. Motivated directly by a real incident: an
  executor skipped video-frame rescue citing "1.6GB", which turned out to be
  a misread of "1,600 snapshots/second" in the transcript, not a real cost —
  nothing caught it at the time.
- Registered **Item 13** in `docs/INFRA_MATURITY_PLAN.md`: a full backend/
  frontend/UX audit against real production use, isolating four thin-shell
  gaps (the four above) from what would be premature "perfumaria" (web
  frontend, vector DB/RAG, multi-user/RBAC) at this project's current scale.

### Fixed
- **`analyst_lens` evidence no longer drowns in PT-BR conversational filler.**
  Found running the scanner against a real course transcript: `salient_terms()`
  surfaced "gente, mercado, cara, pessoas, parte, vocês" — mostly filler words
  ("folks", "dude", "people", "part", "you all"), not domain vocabulary,
  because the stopword list only covered a handful of PT-BR function words.
  Expanded `_STOPWORDS` with common PT-BR conversational filler and discourse
  markers; the same transcript now surfaces actual domain terms ("sinal",
  "backtest", "range") instead.
- **Second wave of PT-BR filler in `analyst_lens` evidence.** Found running
  the (already-patched) scanner against the real ASG transcript end-to-end
  (not the synthetic reproduction above): evidence still surfaced "está,
  exemplo, pessoa, entender" — the verb "estar", generic "exemplo"/"entender",
  and singular "pessoa" (only the plural "pessoas" had been excluded).
  Extended `_STOPWORDS` accordingly.
- **Third wave of PT-BR filler in `analyst_lens` evidence.** Same real-transcript
  re-run after the second pass still surfaced "hoje, também" — generic
  temporal/discourse adverbs. Extended `_STOPWORDS` with these plus the
  immediate same-class neighbors (agora, ainda, depois, antes).

### Documentation
- `docs/ARCHITECTURE.md`'s diagram and component table refreshed: fixed stale
  `scripts/extractor/*` paths (the real package is `book_to_skill/`, from the
  1.2.0 packaging refactor) and added everything shipped in Items 11-13 above
  (pre-flight scan, `.srt`/`.vtt`, `sopx`, Blackhat Mode, `run_report.json`,
  the full 6-check audit apparatus). Dated at the top so the next refresh
  doesn't have to guess how stale it is.
- Clarified the two install paths so they are not confused: **`git clone` into a
  skills folder** registers the `/book-to-skill` agent skill (Copilot
  CLI / Amp / other compatible agents), while **`pip install book-to-skill`** installs only the standalone
  extraction CLI and does not register the skill. README and the docs landing now
  show both explicitly.
- README now leads with the measured headline (24×–51× fewer tokens than a
  context-dump) and a 3-step "how it works", so the value lands in the first
  screen instead of being buried mid-page.

### Security
- **DOCX XXE / Billion Laughs hardening** — the DOCX extractor now scans the
  archive and rejects any XML part that declares a DTD or entities before
  parsing, blocking XML external-entity and entity-expansion attacks (#53, #54).
- **Subprocess argument-injection hardening** — file paths are absolutised
  before being passed to `pdftotext` / `pdfinfo` / `ebook-convert`, so a filename
  starting with `-` cannot be interpreted as a command-line option (#53, #54).
- **Dependency CVE review on pull requests** — a `dependency-review` CI job
  flags any newly introduced dependency carrying a moderate-or-higher CVE (or a
  denied license) and posts the findings as a PR comment. Dependabot now also
  covers the `pip` ecosystem.

### Changed
- **The `pdf` extra now installs `pypdf` instead of the deprecated `PyPDF2`**
  (`pip install book-to-skill[pdf]`). `pypdf` is the maintained successor;
  `PyPDF2` is end-of-life and no longer receives security fixes (#54).

### Fixed
- Text files (`.txt`, `.md`, `.rst`, `.adoc`, `.html`, `.rtf`) saved as UTF-16 or
  UTF-32 (e.g. Windows Notepad "Unicode" or PowerShell output) are now decoded by
  their byte-order mark instead of being read as `cp1252`/`latin-1` mojibake.
- The dependency-free RTF fallback (used when `striprtf` is not installed) now
  decodes `\uN` unicode escapes — smart quotes, dashes, accented letters — instead
  of dropping them and leaving only the ASCII fallback character.
- The stdlib HTML parser (the fallback for HTML files and EPUB extraction when
  BeautifulSoup is not installed) no longer decodes HTML entities twice, so
  double-encoded entities such as `&amp;amp;` survive intact.
- The dependency-free DOCX fallback (used when `python-docx` is not installed)
  now reconstructs tables as tab-joined rows in document order, instead of
  flattening each cell onto its own line.
- The dependency-free EPUB extractor (used when `ebooklib` is not installed) now
  reads content in true spine (reading) order instead of manifest order, so
  chapters are no longer scrambled. Content documents not listed in the spine are
  still included (appended after the spine content).

## [1.2.0] — 2026-06-17

### Added
- **Installable Python package.** The extractor is now a proper `book_to_skill`
  package with a `pyproject.toml` (hatchling build backend), a `book-to-skill`
  console script, and `python -m book_to_skill`. Optional extractors are exposed
  as extras (`epub`, `pdf`, `docx`, `rtf`, `technical`, `all`); the base install
  stays dependency-free with stdlib fallbacks. `requires-python = ">=3.9"`.
  `scripts/extract.py` is kept as a thin shim so the existing skill flow is
  unchanged (#34, #35, #48).
- **Markdown / AsciiDoc heading detection.** Structure detection recognizes ATX
  headings (`#`, `==`) as chapters when no numeric "Chapter N" headings are
  present, fixing a zero-chapter result for `.md` / `.adoc` sources. Headings
  inside fenced code blocks are ignored (#44).
- **setext / reStructuredText underline headings** — a title line over a row of
  `=` or `-` is now detected, so `.rst` and setext-style Markdown no longer
  report zero chapters. Guarded against thematic breaks, table borders, and YAML
  front matter (#51).
- **More chapter languages.** Chapter-word detection now covers French, German,
  Italian, and Dutch (`Chapitre`, `Kapitel`, `Capitolo`, `Hoofdstuk`), and
  heading titles starting with `Ü`/`Û`/`Ý`/`Þ` (e.g. "Überblick") are accepted (#49).
- **Multilingual table-of-contents detection** — Chinese, Japanese, French,
  German, Italian, and Dutch (#44).

### Fixed
- **Full-width Arabic digits in CJK chapter headings** — `第１章` (U+FF10–FF19),
  common in Japanese typesetting, is now detected like `第1章` (#46).
- **Parser errors are no longer swallowed silently.** Unexpected exceptions in
  any extractor are logged to stderr (extractor name + exception type) while the
  fallback chain still returns `None` and continues, so corrupt files and
  encoding errors are diagnosable (#47, #50).
- **All-punctuation ATX "titles"** (e.g. a `=====   =====` table border) are no
  longer miscounted as chapters (#51).
- **Package imports on interpreters that evaluate annotations eagerly.** Added
  `from __future__ import annotations` to every module using PEP 604 unions
  (`str | None`), so the package imports and runs cleanly on Python 3.9 (#34).

### Security
- **CI security scanning** — CodeQL (Python, security-and-quality + weekly
  schedule), Bandit (gates on HIGH severity; reports MEDIUM+ informationally),
  and Zizmor (GitHub Actions workflow audit, informational), plus a Dependabot
  config for the `github-actions` ecosystem. Known finding to harden next:
  Bandit B314 (`xml.etree.ElementTree.fromstring` in the DOCX parser).

### Changed
- CI test matrix now includes Python 3.9 so the import path above is guarded and
  cannot silently re-break.

## [1.1.0] — 2026-06-12

### Added
- **GitHub Copilot CLI as a first-class target** — the same `SKILL.md` now
  discovers, installs, and runs across GitHub Copilot CLI, Amp, and other
  compatible agents via the open Agent Skills standard. Skill Locations cover 8 discovery paths and
  the script probe walks all of them (#30).
- **`validate_skill.py --lens claude|copilot|amp`** — audits a generated SKILL.md
  against each host's rules; `claude` stays the default for CI back-compat (#30).
- **Attribution banner** — `scripts/banner.txt` is printed at the start of each
  run (best-effort, never fails the run).

### Changed
- `SKILL.md` frontmatter trimmed toward the open-standard minimum and the
  description now names all three hosts so each agent's auto-loader picks it up (#30).
- README headline + "Agent Skills" badge; install/usage sections cover all three
  hosts. `docs/ARCHITECTURE.md` shows per-host destination paths (#30).

### Notes
- `allowed-tools` was dropped from the frontmatter for host-neutrality; the skill
  is conformant on all three hosts (validated with all three lenses). If Claude
  users hit permission-prompt friction, the Bash grant from #18 will be restored
  with Claude-native tokens (Copilot ignores the key either way).

## [1.0.0] — 2026-06-08

First formally tagged release. The converter is stable, multi-format, and
validated on real books.

### Added
- **Multi-format extraction** — PDF, EPUB, DOCX, HTML, Markdown, reStructuredText,
  AsciiDoc, RTF, and MOBI/AZW/AZW3 (via Calibre), through a modular `extractor`
  package with per-format parsers and graceful stdlib fallbacks.
- **`extract.py --check`** — preflight that reports which extractors are installed
  for every format and the exact command to install whatever is missing (#21).
- **Adaptive per-chapter depth** — token budget scales with `BOOK_TYPE × DEPTH`;
  study-depth chapters require a worked example, and the cheatsheet is generated as
  a decision/reasoning layer (decision rules, trees, trade-offs, thresholds, tells)
  rather than a keyword list (#20).
- **`tools/discovery_tax.py`** — measures the "Discovery Loop Tax": tokens a
  context-dump vs a discovery loop vs book-to-skill put into context to answer one
  question, on a real book (#23).
- **Update / fold-in workflow** — merge new sources into an existing skill, keeping
  chapter index, topic index, glossary, patterns, and cheatsheet in sync.
- **GitHub Actions CI** — lint (ruff), test matrix (py3.10–3.13), dependency-free
  smoke test, and SKILL.md Claude-conformance validation (#15, #18).

### Changed
- **README positioning** — copyright & fair-use section, "Beyond books" use cases,
  context-dump / RAG / 1M-window FAQ, and a measured Discovery Loop Tax + real
  per-conversion cost table across four books (#19, #27).
- Default output target is `~/.claude/skills/` for compatible agents, with Amp
  skill directories also supported (#13, #14).

### Fixed
- **Chapter detection** — scans the full text (was capped at 50k chars) and counts
  distinct explicit `Chapter N` / `Capítulo N` headings, rejecting numbered list
  items, inline cross-references, and years; adds Portuguese support (#26).
- **Roman-numeral headings** — `I: Loomings`, `II. The Carpet-Bag` are now detected
  with canonical-numeral validation (#28).
- **EPUB extraction** — resolve OPF-relative hrefs in the stdlib zipfile fallback (#11, #12).
- **Batch resilience** — one bad source is skipped with a warning instead of aborting
  the whole run; explicit input order is preserved (#7).

### Known limitations
- Chapter auto-detection needs explicit `Chapter N` / `Capítulo N` or Roman-numeral
  headings. Books that head chapter bodies with bare titles (e.g. *Moby-Dick*, where
  numerals appear only in the table of contents) or use section titles (e.g. Pro Git)
  do not auto-segment.
- Technical PDFs extracted in text mode may lose heading structure; use technical
  mode (Docling) to preserve tables, code, and headings.

[2.1.1]: https://github.com/carpatia77/sop-extractor/releases/tag/v2.1.1
[2.1.0]: https://github.com/carpatia77/sop-extractor/releases/tag/v2.1.0
[1.3.0]: https://github.com/carpatia77/sop-extractor/releases/tag/v1.3.0
[1.2.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.2.0
[1.1.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.1.0
[1.0.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.0.0
