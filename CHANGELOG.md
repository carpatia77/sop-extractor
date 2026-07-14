# Changelog

All notable changes to **book-to-skill** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Added
- **Subtitle transcript (`.srt`/`.vtt`) support in the extraction pipeline
  (`book_to_skill/parsers/subtitle.py`).** Found running a real Full Conversion
  end-to-end: `preflight_scan.py` and SKILL.md Step 1.5 both treat `.srt`/`.vtt`
  as a first-class `BOOK_TYPE=transcript` source, but `extract.py`/`utils.py`
  had no matching support — `SUPPORTED_EXTENSIONS` never included them, so
  Step 2 failed outright with "Unsupported format '.srt'" on every transcript
  source, book scanned or not. Adds `SUBTITLE_EXTENSIONS` to `config.py`, a
  `subtitle.py` parser (cue-index/timestamp/WEBVTT stripping — same grammar as
  `preflight_scan.py`'s `strip_subtitle_markup`, kept in sync intentionally
  rather than imported, since `preflight_scan.py` is deliberately dependency-free
  standalone tooling), and a dispatch branch in `extract_single_file`.
- **Subtitle transcript (`.srt`/`.vtt`) support in `scripts/preflight_scan.py`.**
  Previously these fell through to the generic low-confidence default (no real
  signal), so a video-course transcript — exactly the material Item 11 targets
  — never got the reverse-engineering candidacy check. Cue indices, timestamps,
  and WEBVTT/NOTE headers are stripped down to spoken words before sampling, so
  both the tabular/burst heuristics and `re_candidate`/`analyst_lens` now score
  real signal. `BOOK_TYPE` is correctly reported as `transcript` (SKILL.md Step
  1.5 option 3), not `text`/`technical`, in both the report and the emitted
  Full Conversion prompt.
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

### Documentation
- Planned the remaining maturity-plan item: **Item 12 — Unified CLI menu
  (`sopx`)**, a thin dispatcher over the existing scripts that doubles as 1:1
  scaffolding for a future frontend (spec only, no pipeline code yet).
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

[1.2.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.2.0
[1.1.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.1.0
[1.0.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.0.0
