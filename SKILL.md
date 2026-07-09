---
name: book-to-skill
description: "Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, plain text, RTF, MOBI/AZW with Calibre) into structured agent skills that extract deterministic decision-logic as First Principles and Standard Operating Procedures (SOPs). Use when the user wants to operationalize an author's method into executable step-by-step procedures, apply it while working, or build a reusable decision base from a file."
---

<!--
Cross-agent notes (informational; ignored by host agents):
  - Compatible skill roots: GitHub Copilot CLI (~/.copilot/skills, ~/.agents/skills,
    .github/skills, .claude/skills, .agents/skills), Amp (.agents/skills,
    ~/.config/agents/skills, ~/.config/amp/skills), Claude Code (~/.claude/skills).
  - `allowed-tools` is intentionally omitted to stay agent-neutral: Copilot CLI uses
    `shell`/MCP-server names, Claude uses `Bash`/`Read`/`Write`/`Glob`/`Grep`, Amp
    adds `shell_command`. The skill needs shell (to run extract.py) and file
    read/write — each host will prompt for those on first use.
  - Argument hint: <path-to-document-folder-or-glob>... [skill-name-slug]
-->

# Book-to-Skill Converter

Transform written knowledge into actionable agent skills by extracting structure — not producing summaries.

## Philosophy

Books hide deterministic decision-logic inside prose. This skill extracts that
logic as two artifacts: **First Principles** (the irreducible truths the
author's method rests on) and **Standard Operating Procedures** (the executable
step-by-step the author actually uses).

**Extract logic, not prose.** A skill is not a book report — it is a decision
engine.

**Determinism with honesty (ANTI-FABRICATION RULE).** Convert content into a
SOP *only when the author provides procedural substance*. When the author is
explicitly probabilistic or heuristic, capture it as a **Heuristic** (an
if-then under uncertainty), NOT a fabricated deterministic SOP. Never invent
steps, thresholds, or ordering the source does not contain. Every SOP and
every Principle must be traceable to its chapter.

**First Principle — admission rubric.** A line qualifies ONLY if it is:
  1. an *assertion* (a claim, not a topic);
  2. *causal or foundational* — other ideas in the book derive from it;
  3. *irreducible* — it cannot be decomposed into a more basic claim from the
     same book.
Format: claim + the "because" + what it lets you stop debating.

**Preserve the author's precision.** Exact framework names, exact thresholds.
A named procedure keeps its name.

**Layer depth appropriately.** Simple books → simple skills. Dense books →
reference files and on-demand chapters.

---

## Modes of Operation

Four paths available. Route based on what the user asks:

### 1. Full Conversion (Default)
**Trigger:** User provides one or more document/directory/glob paths without special instructions
**Action:** Run all steps below (Steps 0–9)
**Output:** Complete skill with SKILL.md, chapters/, glossary, first_principles, sops

### 2. Analyze Only
**Trigger:** User says "analyze", "just extract", or "I want to review before generating"
**Action:** Run Steps 0–3, then produce a structured extraction report (frameworks, principles, techniques found). Stop — do NOT generate skill files.
**Output:** Analysis report for user review

### 3. Generate from Prior Analysis
**Trigger:** User has existing analysis notes or previously ran analyze-only
**Action:** Skip Steps 0–3, use the provided analysis as input, run Steps 4–9
**Output:** Skill files from the provided analysis

### 4. Update / Fold-in (Existing Skill)
**Trigger:** User provides one or more new source paths and indicates they want to update an existing skill (either by pointing to the existing skill folder, providing a skill slug that already exists in `SKILLS_HOME`, or explicitly requesting an update).
**Action:** Run Step 0 (out-of-scope check), Step 1 (validate inputs), Step 1.5 (identify book type), and Step 2 (extract new files). Then skip to Step 5 (identify/detect existing skill path) and run the **Update / Fold-in Workflow** to merge the new content into the existing skill files.
**Output:** Updated existing skill with new/revised chapter summaries and merged indexes/glossaries.

---

## Skill Locations

This converter can run from multiple skill systems. When looking for this converter's helper script or writing the generated book skill, prefer these locations in order:

1. GitHub Copilot CLI personal skills: `~/.copilot/skills/`
2. Cross-agent personal skills (Copilot + Amp): `~/.agents/skills/`
3. Claude Code personal skills: `~/.claude/skills/`
4. Project-local Copilot skills: `.github/skills/`
5. Project-local Claude skills: `.claude/skills/`
6. Project-local Amp / Copilot skills: `.agents/skills/`
7. Amp global skills: `~/.config/agents/skills/`
8. Amp legacy global skills: `~/.config/amp/skills/`

For **generated** book skills, pick a destination that the user's host agent can actually discover (see Step 5). When more than one valid root exists, ask the user once and remember the answer for the session — do not silently default.

---

## Step 0 — Out-of-scope check

If no arguments are provided, stop and respond:
> "book-to-skill requires a supported document path, folder, or glob pattern. Usage: `book-to-skill <path-to-document-folder-or-glob>... [skill-name-slug]`"

Throughout the workflow:
- Identify the input paths and the optional skill slug.
- If the last argument is not a file, folder, or glob that exists or matches any files, and it looks like a skill slug (e.g. lowercase hyphens, alphanumeric), treat it as `SKILL_NAME`.
- Treat all other arguments as the list of `INPUT_PATHS`.
- If any input path is an existing skill directory (contains `SKILL.md` and a `chapters/` sub-folder), or if `SKILL_NAME` matches an existing skill slug in `SKILLS_HOME`, flag this run as an **Update/Fold-in** operation (Mode 4).

---

## Step 1 — Validate input

Verify that there is at least one supported file, directory, or glob pattern among the `INPUT_PATHS`.
For directories and globs, expand them to find matching supported files (`.pdf`, `.epub`, `.docx`, `.txt`, `.md`, `.markdown`, `.rst`, `.adoc`, `.html`, `.htm`, `.rtf`, `.mobi`, `.azw`, `.azw3`).

If no supported files are found, stop with a clear error message.

---

## Step 1.5 — Identify content type

If the answers to this step (and Steps 4, 5, 5.5) are being pre-supplied up front for an unattended Full Conversion rather than asked live, review them first against `docs/EXTRACTION_PREFLIGHT_CHECKLIST.md` — a wrong `BOOK_TYPE` here is the single most expensive mistake in this workflow to discover after the fact.

Before extracting, ask the user:

> "What kind of content do these sources have? This helps me choose the best extraction method.
>
> 1. **Technical** — has code blocks, tables, formulas, diagrams (e.g. programming books, academic papers, architecture guides)
> 2. **Text-heavy** — mostly prose, few or no tables/code (e.g. management, productivity, narrative non-fiction)
> 3. **Video course transcript** — an already-transcribed video course/training (SRT/VTT or timestamped text), where structure comes from topic/module changes, not book chapters
> 4. **Not sure** — I'll use the fast method and warn you if quality seems limited"

Store the answer as `BOOK_TYPE`:
- Option 1 → `BOOK_TYPE=technical`
- Option 2 → `BOOK_TYPE=text`
- Option 3 → `BOOK_TYPE=transcript`
- Option 4 → `BOOK_TYPE=text`

**If `BOOK_TYPE=technical`**, inform the user before proceeding:
> "📐 Technical mode selected — using Docling for structure-aware extraction (tables, code blocks, formulas preserved as markdown). This takes ~1.5s per page, so expect a few minutes for longer sources. Starting now…"

**If `BOOK_TYPE=text`**, inform:
> "📄 Text mode selected — using the fastest suitable extractor for each file type. Plain text/Markdown/HTML are usually ready in seconds; PDFs use pdftotext when available."

**If `BOOK_TYPE=transcript`**:

If `INPUT_PATHS` contains more than one transcript file, treat this as a **multi-part course**: assign each file a `PART_ID` (`part1`, `part2`, ... in the order given, or matching an explicit part number in the filename/course material if present — e.g. `parte3-transcricao.srt` → `part3`; never renumber based on assumptions the user hasn't confirmed). Each part is processed through Steps 2–7 independently but contributes modules to the **same** skill, with module numbering continuing across parts (part1's last module is `mod04`, part2 starts at `mod05`, etc.) — see Step 3 for how cross-part chronology is preserved.

Ask one follow-up (a factual input, not an approval — needed to decide whether frame extraction runs at all, and per-part for multi-part courses):
> "🎬 Video course transcript mode<multi-part: ' — N parts detected'>. Do you also have the video file(s) this transcript came from? If yes, give me the path for each part (or say which parts you have video for) — I'll pull still frames at the moments the transcript points at something visual ('look at this', 'olha aqui') without describing it fully in words. If no, I'll extract from the transcript text alone."

Store the answer as `VIDEO_PATH` for a single-part course, or as a `PART_ID → video path` map for multi-part (a part with no video answer simply skips Step 7.5 for that part — it is not an error, and does not block the other parts). Then inform:
> "📼 Transcript mode selected — segmenting by topic/module instead of book chapters. First Principles, SOPs, and Heuristics extraction works exactly as with a book."

---

## Step 2 — Extract text from the source documents

Run the extraction script, passing the input paths:

```bash
SCRIPT_PATH=""
for candidate in \
  "$HOME/.copilot/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.claude/skills/book-to-skill/scripts/extract.py" \
  ".github/skills/book-to-skill/scripts/extract.py" \
  ".claude/skills/book-to-skill/scripts/extract.py" \
  ".agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/amp/skills/book-to-skill/scripts/extract.py"
do
  if [ -f "$candidate" ]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

if [ -z "$SCRIPT_PATH" ]; then
  echo "Could not find scripts/extract.py for book-to-skill" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" "$SCRIPT_PATH" $INPUT_PATHS --mode <BOOK_TYPE> --install-missing ask
```

Before extraction, the script checks optional Python packages needed for the detected format. If a better extractor is missing, it prompts the user with the available fallback. Non-interactive sessions default to fallback unless install mode is explicitly `yes`.

**Tip — preflight the environment:** run `"$PYTHON_BIN" "$SCRIPT_PATH" --check` to print a per-format report of which extractors are installed and the exact command to install whatever is missing, without processing any file. Useful when a user reports a setup or quality problem.

This creates:
- `<tempdir>/book_skill_work/full_text.txt` — combined extracted text of all sources with clear visually demarcated boundaries.
- `<tempdir>/book_skill_work/metadata.json` — overall combined size, words, pages, token counts, and a detailed list of individual processed `sources`.

Read `<tempdir>/book_skill_work/metadata.json` to inspect the results.

---

## Step 2.5 — Pre-flight cost estimate

Read `<tempdir>/book_skill_work/metadata.json` and present the user with an estimate **before doing any generation**:

```
📖 Sources detected: <total_sources> source(s)
<list each source filename and format from the sources metadata list>
📄 Combined Pages/Sections: ~<N> | Words: ~<N> | Total tokens: ~<N>K

💰 Estimated token cost (Full Conversion / Update):
   Input  (reading + prompts): ~<N>K tokens
   Output (skill files generated/updated):  ~<N>K tokens
   Total:                           ~<N>K tokens

   Reference prices (as of 2025):
   Claude Sonnet 4.5 → ~$<X> USD
   Claude Haiku 4.5  → ~$<X> USD

   ⏱  Estimated time: ~<N> minutes

📁 Files to be generated/updated:
   SKILL.md + chapter files + glossary + first_principles + sops

➡  Proceed with Full Conversion / Update? (or type "analyze only" to preview first)
```

**How to estimate:**
- Input tokens ≈ `estimated_tokens` from metadata × 1.3 (prompts overhead per chapter pass)
- Output tokens ≈ chapters × per-chapter budget + 4,000 (SKILL.md) + 4,500 (glossary + first_principles + sops)
  - Per-chapter budget midpoint by `BOOK_TYPE` (DEPTH is decided later in Step 4 and can raise it): `text` ≈ 1,000, `technical` ≈ 1,800. If the user has already indicated reference-only vs deep study, use the matching row of the Step 7 matrix.
- Price: Sonnet input=$3/MTok output=$15/MTok — Haiku input=$0.80/MTok output=$4/MTok

Wait for the user to confirm before proceeding. If they say "analyze only", switch to Mode 2.

---

## Step 2.6 — REPL-style access for large books (> 50k tokens)

Inspired by the Recursive Language Model (RLM) paradigm: treat `full_text.txt` as a queryable corpus, not a single read. Loading the whole file into context burns budget you will need later for generation.

For books over ~50k tokens, prefer programmatic probes over `Read(full_text.txt)` without bounds:

```bash
# Size check before any Read
wc -w "$FULL_TEXT_PATH"

# Find chapter offsets without loading the whole file
grep -n -E "^\s*(Chapter|CHAPTER)\s+[0-9]+" "$FULL_TEXT_PATH" | head -40

# Pull only the chapter you need (lines start..end inclusive)
sed -n '<start>,<end>p' "$FULL_TEXT_PATH"

# Verify a framework is actually mentioned before claiming it in SKILL.md
grep -c -i "westrum\|dora" "$FULL_TEXT_PATH"

# Targeted Read with offset/limit avoids dumping the full file
# Read(file_path=full_text.txt, offset=<line>, limit=<lines>)
```

Use this approach for Step 3 (structure analysis), Step 7 (per-chapter summaries), and Step 8 (glossary / first_principles extraction). On books under 50k tokens, a single `Read` is fine.

Why this matters: a 200-page book is ~75k tokens. Re-reading it once per chapter (28 passes) costs ~2M input tokens; using grep + sed to pull only relevant slices keeps generation cost proportional to the output, not the source.

---

## Step 3 — Analyze book structure

**If `BOOK_TYPE=transcript`**, skip the book-chapter detection below and instead:
- Identify **course title**, **instructor(s)**, and recording/publication date (for `source_date`, if the course maps into a Set — see Set-Level Workflows).
- Segment by **topic/module change**, not book chapters. Look for, in order of preference:
  1. Explicit module markers in the transcript itself ("Module 3", "Part 2", "Lição 4").
  2. Topic-shift signals: a new question/theme introduced after a natural pause, or a repeated framing phrase the instructor uses to start a new segment.
  3. Fallback: chunk by fixed duration (15–20 min per segment) if no natural segmentation exists — note this fallback explicitly in the extraction report, don't silently pretend it's author-intended structure.
- For each segment, record its **start and end timestamp** (from the transcript's own timestamp markers) — this is required later for optional frame extraction (Step 7.5) and for `## Timestamp` in each module file (Step 7).
- **Multi-part courses**: run this segmentation **separately per part** (a part's timestamps are local to its own video/transcript and restart from zero — never compare a part2 timestamp to a part1 timestamp as if they shared a timeline). Carry the `PART_ID` alongside each segment's timestamps; module numbering is still global and sequential across parts (part1 → mod01–mod04, part2 → mod05–mod07, ...), assuming parts are processed in course order. If part order is ambiguous (filenames don't indicate it and the user hasn't said), ask — do not guess, the same discipline as Chronology in Step 5.5.
- Then skip directly to the "Analyze Only" branch below or, in Full Conversion, to Step 4 — the rest of Step 3 (chapter-heading regex, ToC parsing) does not apply.

**Otherwise (`BOOK_TYPE=technical` or `text`)**, read the first 8,000 characters of the extracted `full_text.txt` to identify:
- Book **title** and **author(s)**
- **Chapter structure** (look for "Chapter N", "PART I", numbered headings, table of contents)
- **Core themes** and subject domain
- Approximate number of chapters

Then read the Table of Contents section if present to map all chapters.

**If mode is "Analyze Only":** produce the extraction report now and stop. Structure:
```
## Extraction Report — <Title>

### First Principles
- **<Principle stated as an assertion>** — because <causal reason>.

### Standard Operating Procedures (SOPs)
- **<SOP Name>**: <Trigger / Steps / Failure modes>

### Heuristics & Anti-patterns
- **<What to avoid / Heuristic>**: <why it fails or when to lean toward action>

### Suggested Skill Name
`{author-lastname}-{core-concept}` — e.g. `cialdini-influence`

### Chapters Detected
| # | Title | Key Principles / SOPs |
```
(For `BOOK_TYPE=transcript`, header reads "### Modules Detected" and the table gains a `Timestamp` column: `| # | Title | Timestamp | Key Principles / SOPs |`.)

---

## Step 4 — Ask purpose (Full Conversion only)

Before generating, ask the user:

> "What should this skill help you do? (Pick one or more)
> 1. Apply the author's principles/SOPs while working
> 2. Think with the author's mental models
> 3. Reference specific chapters and concepts
> 4. All of the above"

Use the answer to weight what gets highlighted in the SKILL.md Core section.

**Derive `DEPTH` from the answer (no extra prompt):**
- Answer is **only** option 3 (reference) → `DEPTH=reference` — lean, fast-lookup chapters.
- Answer includes option 1, 2, or 4 → `DEPTH=study` — deeper chapters with more worked detail, examples, and reasoning.

`DEPTH` and `BOOK_TYPE` together set the per-chapter token budget in Step 7. Do **not** ask a separate "study vs reference" question — it is inferred here. (In Modes 2/3, where Step 4 is skipped, default `DEPTH=study`.)

---

## Step 5 — Determine skill name

If `SKILL_NAME` was provided, use it as the skill slug.
Otherwise, propose two options and let the user choose:
- **By author-concept**: `{author-lastname}-{core-concept}` (e.g. `cialdini-influence`, `meadows-systems`)
- **By title**: lowercase hyphens from book title (e.g. `designing-data-intensive-apps`)

Default to author-concept format if the book has a strong methodological identity.

Choose the destination skill root (`SKILLS_HOME`). Probe the user's filesystem for existing skill homes and pick by **the host the user is running in**:

| Host agent | Personal skill root (probe in order) | Project-local root |
|---|---|---|
| **GitHub Copilot CLI** | `~/.copilot/skills` → `~/.agents/skills` | `.github/skills` → `.claude/skills` → `.agents/skills` |
| **Amp** | `~/.agents/skills` → `~/.config/agents/skills` → `~/.config/amp/skills` | `.agents/skills` |
| **Claude Code** | `~/.claude/skills` | `.claude/skills` |

Selection rules:
1. If **exactly one** of the host's candidate roots exists on disk, use it without asking.
2. If **none** exist (fresh machine), ask the user which root to create — present the host-appropriate options and remember the choice for the session. Do not silently pick.
3. If the user explicitly asked for project-local output, prefer the project-local row.
4. If you cannot identify the host, ask: "Which agent are you running this in — GitHub Copilot CLI, Amp, or Claude Code?"

Set `SKILLS_HOME` to the selected root and check if `$SKILLS_HOME/<skill_name>/` already exists.
If it does, prompt the user to choose:
1. **Update / Fold-in** (Mode 4) — integrate new files/content into the existing skill components.
2. **Overwrite** — delete and regenerate the skill from scratch.
3. **Rename** — append `-2` or use a different custom slug.

If the user selects **Update / Fold-in**, proceed immediately to the **Update / Fold-in Workflow** section after Step 2.5 (skipping Steps 3, 4, 6, 7, 8, 9).

---

## Step 5.5 — Lineage Detection (opt-in Set membership)

Before creating the skill directory, check whether this book might belong to an existing author lineage already present in `$SKILLS_HOME`.

1. Derive `author-lastname` from the author(s) identified in Step 3.
2. Scan `$SKILLS_HOME/*/SKILL.md` for frontmatter whose `source_title` or author byline matches `author-lastname` (case-insensitive substring match). Also check for an existing `$SKILLS_HOME/<author-lastname>-set/set_manifest.json`.
3. **If no matches**: proceed to Step 6 normally. Say nothing — this is the common case and shouldn't add friction to single-book extractions.
4. **If ≥1 match found**: stop and ask the user — do not guess:
   > "Detectei que isto pode pertencer à mesma linhagem de **<author-lastname>**: <list of matched skill names with their `source_date`>. Este novo livro (\"<title>\") é cronologicamente **anterior**, **posterior**, ou **não relacionado** a essas fontes? Se relacionado, qual a data de publicação (ano basta)?"

   Never infer chronology from filename, edition number, or "vibes." If the user says "not related," drop it and proceed normally — do not create or touch any manifest.

5. **If the user confirms lineage** and supplies a date:
   - Set `source_date` for this skill's frontmatter (Step 9) from the user's answer.
   - After the skill is fully generated (end of Step 9), create or update `$SKILLS_HOME/<author-lastname>-set/set_manifest.json`:
     - If it doesn't exist, create it with the matched sibling(s) plus this new skill, `members` sorted ascending by `date`.
     - If it exists, insert the new member at the chronologically correct position (do not blindly append).
   - Use relative `skill_path` values (e.g. `"../<skill_name>"`) exactly as in the existing Set-Level Workflows schema — this is the same manifest format, just auto-populated instead of hand-written.
6. Do **not** run the Temporal Evolution Audit itself here — that only happens via the opt-in offer in **Step 9.7**, after generation is complete and the set has ≥2 members.

---

## Step 6 — Create skill directory structure

```bash
mkdir -p "$SKILLS_HOME/<skill_name>/chapters"
```

---

## Step 7 — Generate chapter summaries

**TOKEN BUDGET RULE — CRITICAL (adaptive):**

The per-chapter budget scales with `BOOK_TYPE` and `DEPTH`. Technical chapters need room for code and tables; study depth needs room for worked reasoning. Pick the budget from this matrix:

| | `DEPTH=reference` | `DEPTH=study` |
|---|---|---|
| `BOOK_TYPE=text` | 800–1,200 tokens | 1,000–1,800 tokens |
| `BOOK_TYPE=technical` | 1,200–1,800 tokens | 2,000–3,000 tokens |

- These are per-file targets, not hard caps — a dense chapter may run over, a thin one under. Density still beats length (Quality Rule #3): never pad to hit a number.
- Files are loaded on-demand, so a larger chapter only costs tokens when that chapter is actually read.
- When in doubt between two cells (e.g. mixed-content book), use the lower budget and let depth come from precision, not volume.

**`DEPTH=study` is earned with content, not a bigger number.** The standard section template (Core Idea → Connects To) naturally lands a dense prose chapter around 700–900 tokens. To reach the study budget *honestly* — not by padding — a study-depth chapter must add concrete material:
- **Reproduce one worked example or artifact** from the chapter (e.g. the example press release, a sample dialogue, a filled-in template, a decision the author walks through) under a `## Worked Example` section. This is the single biggest lever and the main thing a learner returns for.
- **Expand the "How" of each framework** into explicit steps or criteria, not a one-liner.
- **Add a short "Why it works / failure mode" note** to the top 1–2 frameworks.

If a chapter genuinely has no worked example and resists expansion, let it land below the study floor rather than padding — and note that the chapter is thin in its Core Idea. A `reference`-depth chapter, by contrast, deliberately omits worked examples and keeps only the decision-ready essentials.

For EACH chapter/major section (or, for `BOOK_TYPE=transcript`, each module) identified in Step 3:

Read the corresponding section of the extracted `full_text.txt` (use character offsets, or grep for chapter headings / the module's timestamp range).

Create `$SKILLS_HOME/<skill_name>/chapters/ch<NN>-<slug>.md` using the structure below (for `BOOK_TYPE=transcript`, name it `chapters/mod<NN>-<slug>.md` instead — everything else about the template is identical).

**Adapt emphasis based on `BOOK_TYPE`:**
- `technical` → prioritize "Code Examples", "Reference Tables", and SOPs with exact syntax
- `text` → prioritize "First Principles", "SOP", and "Heuristics"
- `transcript` → prioritize "First Principles", "SOP", and "Heuristics" exactly like `text`; additionally include `## Timestamp` (below) and, if Step 7.5 extracted a relevant frame, a `## Visual Reference` section

```markdown
# Module N: <Full Title>   <!-- "# Chapter N: <Full Title>" for BOOK_TYPE=technical/text -->

## Timestamp *(BOOK_TYPE=transcript only — omit otherwise)*
`[<start HH:MM:SS> – <end HH:MM:SS>]` (single-part course)
`[Part <N>, <start HH:MM:SS> – <end HH:MM:SS>]` (multi-part course — always name the part, since the timestamp alone is only local to that part's video)

## Core Idea
<1–2 sentences: the single most important thing this module/chapter teaches>

## First Principles
<!-- Each line MUST pass the admission rubric in Philosophy. Omit the whole
     section if the chapter has none — do NOT pad. -->
- **<Principle stated as an assertion>** — because <causal reason>.
  Lets you stop debating <X>. (source: this chapter)

## Standard Operating Procedure (SOP)
<!-- Generate ONLY if the chapter contains real procedural substance.
     If the author gives no procedure, omit this section and use Heuristics. -->
### SOP: <name of the task this procedure solves>
- **Trigger / Precondition**: <when this runs>
- **Steps**:
  1. <imperative action>
  2. <imperative action — keep the author's exact thresholds/numbers>
- **Decision points**: <if X → branch A; if Y → branch B>
- **Done when**: <termination condition>
- **Failure modes**: <what breaks it and the observable tell>

## Heuristics (under uncertainty)
<!-- Probabilistic if-then the author commits to but that is NOT deterministic.
     This is the escape hatch that prevents fake SOPs. Omit if none. -->
- When <signal>, lean toward <action> — confidence/hedge: <author's qualifier>.

## Anti-patterns
- **<What to avoid>**: <why it fails>

## Code Examples *(technical books only — omit if BOOK_TYPE=text)*
<!-- Copy the most instructive snippet from the chapter. Preserve indentation exactly. -->
```<language>
<key code example from this chapter>
```
- **What it demonstrates**: <one line>

## Reference Tables *(technical books only — omit if BOOK_TYPE=text)*
<!-- Reproduce any comparison matrix, parameter table, or decision table from the chapter in markdown. -->

## Worked Example *(DEPTH=study only — omit for DEPTH=reference)*
<!-- Reproduce or reconstruct one concrete example the author works through: a
     sample document, a dialogue, a filled-in template, a before/after, or a
     decision walked end-to-end. This is what makes a study chapter worth its
     budget. Keep it faithful to the source; never copy long raw passages —
     reconstruct the example compactly. -->

## Visual Reference *(BOOK_TYPE=transcript only — omit if Step 7.5 didn't run or found no frame for this module's timestamp range)*
<!-- One line per extracted frame relevant to this module, from frames_manifest.json.
     Never invent a frame reference that isn't in the manifest. -->
![<matched marker phrase, e.g. "olha aqui — b-formation">](../frames/<filename from manifest>)
- **Context**: <the transcript line that triggered this frame extraction>

## Key Takeaways
1. <Actionable insight>
2. <Actionable insight>
3. <Actionable insight>
(3–7 takeaways a practitioner must remember)

## Connects To
- **Ch/Mod N**: <why this chapter/module relates>
- **<Concept>**: <external concept or standard it connects with>
```

---

## Step 7.5 — Frame Extraction for Visual Gaps (transcript courses only)

**Skip this step entirely unless `BOOK_TYPE=transcript` and at least one video path was provided in Step 1.5.** If neither condition holds, go directly to Step 8 — do not mention frame extraction to book extractions.

Run the frame-extraction script against the original transcript file (not the generated module files — it needs the raw timestamps). **For a single-part course**, run it once:

```bash
SCRIPT_PATH=""
for candidate in \
  "$HOME/.claude/skills/book-to-skill/scripts/extract_frames_at_timestamps.py" \
  ".agents/skills/book-to-skill/scripts/extract_frames_at_timestamps.py" \
  "$HOME/.config/agents/skills/book-to-skill/scripts/extract_frames_at_timestamps.py" \
  "$HOME/.config/amp/skills/book-to-skill/scripts/extract_frames_at_timestamps.py"
do
  if [ -f "$candidate" ]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

python3 "$SCRIPT_PATH" <original-transcript-file> --video "$VIDEO_PATH" --output-dir "$SKILLS_HOME/<skill_name>/frames"
```

**For a multi-part course**, run it once per part that has a video, always pointing at the **same** `--output-dir` and passing `--part-id`:

```bash
python3 "$SCRIPT_PATH" <part1-transcript> --video "<part1-video>" --output-dir "$SKILLS_HOME/<skill_name>/frames" --part-id part1
python3 "$SCRIPT_PATH" <part2-transcript> --video "<part2-video>" --output-dir "$SKILLS_HOME/<skill_name>/frames" --part-id part2
```

`--part-id` prevents two parts with a similar-looking timestamp (e.g. part1 at 5:22 and part3 also at 5:22) from silently overwriting each other's frame, and the script merges each run into the shared `frames_manifest.json` instead of overwriting it — skip a part with no video entirely, it's not an error, the manifest just won't have entries for it.

This writes extracted frames plus `frames/frames_manifest.json` (timestamp, `part_id`, matched marker, transcript context for each frame — never construct this mapping yourself, always read it from the manifest the script produced).

For each module whose timestamp range (from Step 3) contains one or more frames from the manifest **with the matching `part_id`**, add a `## Visual Reference` entry to that module's file (Step 7 template) citing the exact filename and context from the manifest. A module with no matching frames simply omits the section — do not force one.

If ffmpeg is not installed or the script errors for a given part, report that part's failure plainly and continue with the remaining parts and the rest of the extraction — this is an enhancement, not a blocker.

---

## Step 8 — Generate supporting files

### glossary.md
Create `$SKILLS_HOME/<skill_name>/glossary.md`:
- Every significant term from the book, alphabetically sorted
- Format: `**Term** — definition (Ch N)`
- Optimize for density. Use tables and tight lists. No introductory fluff. Max 3,500 tokens
  <!-- Budget calibrated against dense technical books (e.g., a dense reference glossary ~3.3k tokens) -->

### first_principles.md
Create `$SKILLS_HOME/<skill_name>/first_principles.md`:
- Every First Principle in the book that passes the admission rubric.
- Grouped by chapter; each entry: assertion + "because" + chapter ref.
- No topics, no definitions (those live in glossary.md). Optimize for density. Max 3,000 tokens.
  <!-- Budget calibrated to accommodate dense principles (e.g., a dense principles file ~2.2k tokens) -->

### sops.md
Create `$SKILLS_HOME/<skill_name>/sops.md`:

This is the operational core of the skill — a library of executable procedures,
not a keyword list. Prioritize, in order:
1. **SOPs** — named, with Trigger → Steps → Decision points → Done when → Failure modes.
2. **Decision trees / flowcharts** — for branches with more than two outcomes.
3. **Thresholds & defaults** — the exact numbers/ratios the author commits to.
4. **Heuristics** — if-then under uncertainty (clearly marked as non-deterministic).
5. **Tells & smells** — fast recognition heuristics ("if you see X, you're in Y").

Every entry must let the reader *act*, not just recognize a term.
Format as compact procedures and tables. Optimize for density. No introductory fluff. Max 4,000 tokens.
<!-- Budget calibrated against procedural-heavy books (e.g., a procedure-heavy SOPs file ~3.5k tokens) -->

---

## Step 9 — Generate the master SKILL.md

**CRITICAL TOKEN BUDGET: Keep SKILL.md body under 4,000 tokens.**
Compaction truncates from the END — put the most important content FIRST.

Create `$SKILLS_HOME/<skill_name>/SKILL.md`:

- `source_id`: a short, lowercase slug (e.g., `src1`, `src2`).
- `source_date`: publication or recording date (`YYYY-MM-DD`). If exact day/month is unknown, use `YYYY-01-01`.
- `source_role`: choose from `primary_theory`, `practitioner_book`, `live_training` (`BOOK_TYPE=transcript` always maps to `live_training`).
- `source_title`: the full title of the source.

```markdown
---
name: <skill_name>
source_id: <short_slug>
source_date: <YYYY-MM-DD>
source_role: <primary_theory | practitioner_book | live_training>
source_title: "<Full Title>"
description: "Knowledge base from \"<Full Title>\" by <Author(s)>. Use when operationalizing <author>'s method as SOPs and first principles, studying the book, or referencing its concepts."
---

<!-- argument-hint: [topic, framework name, or chapter number] -->

# <Full Title>
**Author**: <Author(s)> | **Pages**: ~<N> | **Chapters**: <N> | **Generated**: <YYYY-MM-DD>

## How to Use This Skill

- **Without arguments** — load core principles/SOPs for reference
- **With a topic** — ask about `replication`, `pricing`, or another indexed topic; I find and read the relevant chapter
- **With chapter** — ask for `ch05`; I load that specific chapter
- **Browse** — ask "what chapters do you have?" to see the full index

When you ask about a topic not covered in Core First Principles & SOPs below, I will read
the relevant chapter file before answering.

---

## Core First Principles & SOPs
<!-- ~2,000 tokens: the author's load-bearing principles and the SOPs that
     operationalize them. Preserve exact names.
     This is a toolkit, not a summary. -->

<generate 2,000 tokens of the most critical frameworks and insights here>

---

## Determinism Profile

📐 **<book_determinism_pct>%** SOP-backed (deterministic) · **<remainder>%** heuristic/uncertain
📊 Procedural coverage: <coverage_pct>% of chapters

*Computed structurally — not a model self-assessment.*

---

## Chapter Index
<!-- For BOOK_TYPE=transcript: header is "## Module Index", links point at
     chapters/mod<NN>-<slug>.md, and the table gains a Timestamp column
     between Title and Key Principles/SOPs. -->

| # | Title | Key Principles / SOPs |
|---|-------|----------------|
| [ch01](chapters/ch01-<slug>.md) | <Title> | <framework1>, <framework2> |
| [ch02](chapters/ch02-<slug>.md) | <Title> | <framework1>, <framework2> |
...

## Topic Index

<!-- Alphabetical. Major terms/frameworks → chapter(s) that cover them. -->
- **<Term>** → ch<N>[, ch<N>]
- **<Term>** → ch<N>

## Supporting Files

- [glossary.md](glossary.md) — all key terms with definitions
- [first_principles.md](first_principles.md) — every load-bearing principle, by chapter
- [sops.md](sops.md) — executable procedures, decision trees, thresholds, heuristics

---

## Scope & Limits

This skill covers the book content only. For hands-on implementation in your codebase,
combine with project-specific tools. For topics beyond this book, check related skills
or ask the agent directly.
```

---

## Step 9.5 — Compute Determinism Score

Run the structural scoring script — this is NOT an LLM judgment call, it is a
mechanical count of SOP vs. Heuristic sections already written to disk:

```bash
SCRIPT_PATH=""
for candidate in \
  "$HOME/.claude/skills/book-to-skill/scripts/determinism_score.py" \
  ".agents/skills/book-to-skill/scripts/determinism_score.py" \
  "$HOME/.config/agents/skills/book-to-skill/scripts/determinism_score.py" \
  "$HOME/.config/amp/skills/book-to-skill/scripts/determinism_score.py"
do
  if [ -f "$candidate" ]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

"$PYTHON_BIN" "$SCRIPT_PATH" "$SKILLS_HOME/<skill_name>"
```

This writes `determinism_score.json` to the skill root. Read it and insert the
**Determinism Profile** section into the just-generated master `SKILL.md`
(see template below), using the exact numbers from the JSON — do not estimate,
round only for display (1 decimal max), and do not editorialize on the score.

---

## Step 9.6 — Coherence Audit

After Step 9.5, automatically generate the coherence audit prompt:

1. Create a file `$SKILLS_HOME/<skill_name>/.coherence_audit_prompt.md` with the following content:
   ```markdown
   # Coherence Audit Prompt
   
   Read the following files from this directory:
   - `first_principles.md`
   - `sops.md`
   - `glossary.md`
   
   Do NOT read the individual chapter files unless strictly necessary to confirm a tension.
   
   **Task:** Detect cross-chapter contradictions, scope gaps, and unstated assumption shifts.
   For each candidate pair of claims, try to reconcile them first (e.g. "one is for beginners, one is for advanced"). Only flag if reconciliation fails.
   
   Write a report to `coherence_audit.md` exactly following this template:
   
   # Coherence Audit — <Book Title>
   
   > Generated by a separate, isolated audit pass over first_principles.md and
   > sops.md. This is a flagging report, not a verdict — each item requires
   > human judgment to resolve. Nothing in the skill's core files was modified
   > by this audit.
   
   ## Flagged Tensions
   
   ### 1. <short label>
   - **Type**: direct_contradiction | scope_gap | unstated_assumption_shift
   - **Claim A** (Ch <N>): "<exact or near-exact quote/paraphrase>"
   - **Claim B** (Ch <M>): "<exact or near-exact quote/paraphrase>"
   - **Why flagged**: <1-2 sentences — what fails to reconcile>
   - **Confidence**: low | medium | high
   
   (repeat, max 15 items. If there are no tensions, output an empty list.)
   
   After writing the report, run the validation script:
   
   ```bash
   SCRIPT_PATH=""
   for candidate in \
     "$HOME/.claude/skills/book-to-skill/scripts/validate_coherence_audit.py" \
     ".agents/skills/book-to-skill/scripts/validate_coherence_audit.py" \
     "$HOME/.config/agents/skills/book-to-skill/scripts/validate_coherence_audit.py" \
     "$HOME/.config/amp/skills/book-to-skill/scripts/validate_coherence_audit.py"
   do
     if [ -f "$candidate" ]; then
       SCRIPT_PATH="$candidate"
       break
     fi
   done
   
   python3 "$SCRIPT_PATH" coherence_audit.md --dir .
   ```
   
   If the script passes, add this line to the master `SKILL.md` under Supporting Files:
   `- [coherence_audit.md](coherence_audit.md) — flagged cross-chapter tensions (review required)`
   ```
2. Stop generation and print to the user:
   > "Para isolamento real (evita viés de confirmação), abra uma nova sessão/thread e rode: `[seu-agente] execute a auditoria de coerência usando .coherence_audit_prompt.md`"
   > 
   > *Run the isolated audit session on a different model family than the extraction where possible — a second model is less likely to rubber-stamp the first model's phrasing.*

---

## Step 9.7 — Auto-Trigger Set Audit

If Step 5.5 registered this skill into `$SKILLS_HOME/<author-lastname>-set/set_manifest.json` **and** that manifest now has 2 or more `members`, automatically prepare the Temporal Evolution Audit:

- Follow the exact same procedure as the **Temporal Evolution Audit (author Set)** steps under **Set-Level Workflows** below — generate `.evolution_audit_prompt.md` inside `$SKILLS_HOME/<author-lastname>-set/` and print the isolation handoff instruction.

If Step 5.5 did not run or found no lineage, skip this step entirely — do not mention sets to single-book extractions.

---

## Step 10 — Cleanup and report

```bash
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" - <<'PY'
import os
import shutil
import tempfile
from pathlib import Path
shutil.rmtree(
    os.environ.get("BOOK_SKILL_WORKDIR", Path(tempfile.gettempdir()) / "book_skill_work"),
    ignore_errors=True,
)
PY
```

Then report to the user:

```
✅ Skill created: $SKILLS_HOME/<skill_name>/

📚 Book: <Full Title> — <Author>
📄 Pages: ~<N> | Chapters: <N>

Files generated:
  SKILL.md         — core principles + index   (~X tokens)
  chapters/        — <N> chapter summaries     (~X tokens each, ~X total)
  glossary.md      — key terms                 (~X tokens)
  first_principles.md — load-bearing principles   (~X tokens)
  sops.md          — executable procedures     (~X tokens)
  ─────────────────────────────────────────────────────
  Total skill size: ~X tokens (loaded on-demand, not all at once)
  📐 Determinism: <book_determinism_pct>% SOP-backed | <100-X>% heuristic

💡 Tip: check your agent's session cost/usage command to see actual token usage.

Usage:
  Ask for <skill_name>                  → load core principles/SOPs
  Ask <skill_name> about <topic>        → find and explain a topic
  Ask <skill_name> for ch<N>            → dive into a specific chapter

Reload (if your agent doesn't auto-detect new skills):
  GitHub Copilot CLI:  /skills reload
  Claude Code:         restart the session
  Amp:                 restart the session

Share this skill (Copilot ecosystem, optional):
  gh skill publish $SKILLS_HOME/<skill_name>

Auditoria de coerência preparada em `.coherence_audit_prompt.md` — rode em nova thread para executar.
[Se a malha temporal foi acionada]: Auditoria temporal preparada em `<author-lastname>-set/.evolution_audit_prompt.md` — rode em nova thread para executar.
```

---

## Update / Fold-in Workflow

When performing an Update/Fold-in operation on an existing skill at `$SKILLS_HOME/<skill_name>/`:

### 1. Read Existing Skill Structure
Read and parse the existing skill's files:
- Read `$SKILLS_HOME/<skill_name>/SKILL.md` to parse the existing **Chapter Index**, **Topic Index**, metadata (author, total chapters), and **Core First Principles & SOPs**.
- List all files in `$SKILLS_HOME/<skill_name>/chapters/` to find the highest chapter number (e.g. `ch12`).
- Read `$SKILLS_HOME/<skill_name>/glossary.md`, `$SKILLS_HOME/<skill_name>/first_principles.md`, and `$SKILLS_HOME/<skill_name>/sops.md` to see what terms and principles/SOPs are already indexed.

### 2. Match Content & Identify Revisions vs. Additions
Analyze the new extracted text in `<tempdir>/book_skill_work/full_text.txt` to identify if the new content represents:
- **Updates/Revisions to existing chapters**: If a section of the new content directly updates or expands an existing chapter's topic, read the existing chapter file, merge the new details into it, and rewrite the file.
- **New additions**: If the content introduces new chapters, papers, or separate sections, create **new chapter summary files** under `chapters/`. Start numbering these files after the highest existing chapter number (e.g. if the existing chapters stop at `ch12`, create `ch13-*.md`, `ch14-*.md`, etc.).

### 3. Generate or Update Chapter Summary Files
For each new or revised chapter:
- Read the corresponding section of the extracted new text.
- Follow the formatting guidelines in **Step 7** to build the summary.
- Write/update the file in `$SKILLS_HOME/<skill_name>/chapters/`.

### 4. Merge Supporting Files
- **Merge glossary.md**:
  - Read the existing `$SKILLS_HOME/<skill_name>/glossary.md`.
  - Extract all new terms and definitions from the new content (Step 8 glossary guidelines).
  - Combine and alphabetize the list of existing and new terms.
  - If a term already exists, append the new chapter/source references to it (e.g. `**Term** — definition (Ch 4, Ch 13)`).
  - Rewrite `$SKILLS_HOME/<skill_name>/glossary.md` with the fully merged, alphabetized list.
- **Merge first_principles.md**:
  - Read existing `$SKILLS_HOME/<skill_name>/first_principles.md`.
  - Extract any new principles from the new content (ensuring they pass the admission rubric).
  - Append the new principles (deduplicating by assertion), ensuring consistent formatting, and keeping the total length concise (under 2,500 tokens).
- **Merge sops.md**:
  - Read existing `$SKILLS_HOME/<skill_name>/sops.md`.
  - Extract new SOPs, decision tables, or thresholds.
  - Integrate them cleanly into the sops structure (deduplicating by task name).

### 5. Re-generate the Master SKILL.md
Update the master skill file `$SKILLS_HOME/<skill_name>/SKILL.md`:
- **Metadata**: Increment the chapter count, update the estimated page count, and add the new source names if appropriate. Update the `Generated` date to the current date.
- **Core First Principles & SOPs**: Fold in the most high-impact principles or SOPs from the new content (ensuring the overall file remains under 4,000 tokens).
- **Chapter Index**: Append the new chapters to the index table, linking to the newly created files.
- **Topic Index**: Merge the new topics alphabetically. If an existing topic is also covered in the new chapters, append the new chapter links to its line (e.g. `- **Topic** → ch05, ch13`).
- **Determinism Profile**: Re-run `determinism_score.py` against the updated `chapters/` directory and refresh the Determinism Profile section with the new totals.

### 6. Cleanup and Proceed to Step 9.6
Once the files are successfully written and merged, proceed to **Step 9.6** to optionally generate the Coherence Audit prompt, and then **Step 10** to perform cleanup and print a custom update report summarizing the newly added chapters, merged glossary terms, and updated indices.

---

## Set-Level Workflows

This section can be entered two ways: **manually** (follow the steps below directly), or **automatically** via Step 5.5 (Lineage Detection) + Step 9.7 (Auto-Trigger), which populate the manifest for you and automatically prepare the audit once ≥2 sources exist.

### Temporal Evolution Audit (author-Set pattern)
When multiple skills from the same author or lineage exist, they can be grouped into a **Set** to audit how concepts evolve over time. the set directory is named `$SKILLS_HOME/<author-lastname>-set/`.

1. **Create the Set Manifest**: Create a directory (e.g., `$SKILLS_HOME/<author-lastname>-set/`) and write a `set_manifest.json` listing the member skills in chronological order. The schema is:
   ```json
   {
     "set_id": "<author-lastname>-<domain>",
     "members": [
       {"source_id": "src1", "date": "1990-01-01", "role": "practitioner_book", "skill_path": "../author-book-one"},
       {"source_id": "src2", "date": "2007-01-01", "role": "practitioner_book", "skill_path": "../author-book-two"}
     ]
   }
   ```
   When created by Step 5.5, `set_id` is derived as `<author-lastname>-<core-domain>` and the directory is `<author-lastname>-set/`, but the schema itself is identical whether hand-written or auto-populated.

   **Two members sharing the same `date`** (e.g. two 2025 courses where only the year is known): the Chronology Gate cannot order them from the date alone and will fail with a clear error unless both members also carry an explicit integer `"sequence"` field (lower = earlier):
   ```json
   {"source_id": "course_a", "date": "2025-01-01", "role": "live_training", "skill_path": "../author-course-a", "sequence": 1},
   {"source_id": "course_b", "date": "2025-01-01", "role": "live_training", "skill_path": "../author-course-b", "sequence": 2}
   ```
   Ask the user for this ordering explicitly (same rule as Step 5.5 Lineage Detection) — never infer it from manifest order, filename, or course number.
2. **Generate the Handoff Prompt**: Create `<author-lastname>-set/.evolution_audit_prompt.md` with:
   ```markdown
   # Temporal Evolution Audit Prompt
   
   Read the `set_manifest.json` in this directory to understand the chronological order of the sources.
   For each member skill listed, read its `first_principles.md`, `sops.md`, and `glossary.md`. Do NOT read the full text or chapter files.
   
   **Task**: Track how concepts evolve across the chronological sources. For each concept that appears in ≥2 sources, classify the transition into one of these categories:
   - `introduced`: First appearance.
   - `reaffirmed`: Reaffirmed materially unchanged in a later source.
   - `refined`: Later source adds precision, condition, or threshold without reverting the core rule.
   - `superseded`: Later source EXPLICITLY changes the rule/threshold (requires explicit evidence, never infer from silence).
   - `contradiction_unmarked`: Later source conflicts with earlier, but author doesn't acknowledge the change.
   - `dropped?`: Present earlier, absent later. (Always mark as low confidence. Do NOT treat as superseded).
   
   Always try to reconcile first (e.g., `refined` or `reaffirmed`). Only flag `superseded` or `contradiction_unmarked` if there's explicit evidence.
   
   Write a matrix report to `<author-lastname>_evolution.md` matching this format:
   
   ## <Concept Name>
   | Fonte | Data | Papel | Tratamento | O que mudou |
   |---|---|---|---|---|
   | <source_id> | <date> | <role> | <category> | <description of change> |
   
   - **Estado atual (crème):** [<source_id>/<date>] <surviving formulation>
   - **Estabilidade:** <summary of stability>
   
   **CRITICAL**: In the "O que mudou" column, you MUST use the exact terms and phrasing from the source, rather than free paraphrasing. The structural validator will check for word overlap.
   
   Then, write the distilled surviving state to `<author-lastname>_current.md`. Each line MUST end with a provenance tag `[source_id/date]`:
   - **<Concept Name>** — <surviving formulation>. `[<source_id>/<date>, base: <old_source_id>/<old_date>]`
   
   After generating both files, run the validation script:
   
   ```bash
   SCRIPT_PATH=""
   for candidate in \
     "$HOME/.claude/skills/book-to-skill/scripts/validate_evolution_audit.py" \
     ".agents/skills/book-to-skill/scripts/validate_evolution_audit.py" \
     "$HOME/.config/agents/skills/book-to-skill/scripts/validate_evolution_audit.py" \
     "$HOME/.config/amp/skills/book-to-skill/scripts/validate_evolution_audit.py"
   do
     if [ -f "$candidate" ]; then
       SCRIPT_PATH="$candidate"
       break
     fi
   done
   
   python3 "$SCRIPT_PATH" --dir .
   ```
   ```

3. **Stop and print handoff**:
   > "Para isolamento real (evita viés de histórico), abra uma nova sessão/thread e rode: `[seu-agente] execute a auditoria temporal usando <author-lastname>-set/.evolution_audit_prompt.md`"
   > 
   > *Run the isolated audit session on a different model family than the extraction where possible — a second model is less likely to rubber-stamp the first model's phrasing.*

---

## Quality Rules

1. **Extract structure, not summaries** — capture exact formulations, first principles, SOPs, and anti-patterns; not chapter recaps
2. **Preserve the author's precision** — "The 5 Whys" ≠ "ask why multiple times"; keep exact naming
3. **Density over completeness** — a 1,000-token summary beats a 10,000-token excerpt
4. **Practitioner voice** — write "Use X when Y", not "The book explains X"
5. **Front-load SKILL.md** — compaction keeps the first 5,000 tokens; most important content comes first
6. **Chapter files are on-demand** — they don't count against skill budget until loaded
7. **Never copy raw book text** — always synthesize, summarize, extract signal
8. **Topic index is critical** — it's how the agent navigates to the right chapter file
