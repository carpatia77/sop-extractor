# Infrastructure Maturity Plan (80/20) — Executor Spec

**Audience:** the implementing engineer.
**Goal:** take the project from "advanced prototype, run once by one person on ~5 sources" to a "robust medium-scale tool" — dozens of sources across several author-sets, re-run repeatedly, where you can trust re-runs and catch regressions. **Explicitly NOT enterprise scale** (no orchestrators, vector DBs, K8s, RBAC, compliance frameworks — see "Out of scope" at the end and why).

This plan is the Pareto subset (the ~20% of work that yields ~80% of the maturity gain) distilled from an external architectural review. **Read "Correcting the review's premises" first — the review assumed an automated production data-pipeline; this project is a human-driven toolkit of deterministic validators + an LLM spec (`SKILL.md`). About half of the review's "critical" items are non-issues here.**

---

## Correcting the review's premises (do not skip)

The external review is thorough but built on a wrong mental model. Two facts from the codebase invalidate several of its recommendations:

1. **There is no programmatic LLM integration.** `grep -riE "openai|anthropic|api_key|completion(" scripts/` returns nothing. The "LLM sessions", "regeneration loops", and "isolated audits" are a *human running an agent in a fresh chat session*. Consequences:
   - "Infinite regeneration loop / circuit breaker / max_retries **as code**" → **N/A**. There is no daemon. This becomes a *documented convention* (item 8), not infrastructure.
   - "Set temperature=0 / seed / greedy decoding in every call" → **no call exists to configure**. Becomes a *convention* recorded in the run manifest (item 2), not a code change.
2. **`determinism_score.py` does NOT run extraction multiple times and measure overlap** (the review claims this twice). It counts `### SOP:` headings vs. Heuristics sections in the already-generated chapter/module files, in a single pass (`scripts/determinism_score.py:10,22,32`). It measures *how procedural the content is*, not run-to-run repeatability. Don't build "repeatability" features on top of a misread of this script.

Net: implement the 8 items below. Ignore the review's orchestrator/vector-DB/KG/K8s/RBAC/compliance/multi-thousand-source recommendations — those are enterprise scope the project owner has explicitly excluded.

---

## Current interfaces (ground truth for the items below)

| Script | CLI | Notes |
|--------|-----|-------|
| `scripts/determinism_score.py` | `python scripts/determinism_score.py <skill_dir>` | prints JSON to stdout; needs `<skill_dir>/chapters/` |
| `scripts/verify_concept_presence.py` | `python scripts/verify_concept_presence.py <skill_dir> [--show-absent] [--gate]` | needs `<skill_dir>/first_principles.md` + `transcripts/*.srt`; `--gate` exits 2 on flags |
| `scripts/validate_coherence_audit.py` | `python scripts/validate_coherence_audit.py <audit_file> --dir <skill_dir>` | `run_validation(audit_path, fp_path, sops_path) -> int` |
| `scripts/validate_evolution_audit.py` | `python scripts/validate_evolution_audit.py --dir <set_dir>` | `run_validation(dir_path) -> int`; reads `set_manifest.json`, globs `*_evolution.md` / `*_current.md` |

`set_manifest.json` shape (read by `validate_evolution_audit.load_manifest`, `scripts/validate_evolution_audit.py:15-26`):
```json
{
  "set_id": "<author>-<domain>",
  "members": [
    {"source_id": "src1", "date": "1990-01-01", "role": "practitioner_book", "skill_path": "../skill-one", "sequence": 1}
  ]
}
```
Only `source_id`, `date`, `sequence?` are consumed today; `role` and `skill_path` are read elsewhere. `skill_path` is relative to the set dir.

All new code goes in `scripts/`, all new tests in `tests/`, following the existing convention (pure functions + thin `main()`, pytest with tempdir fixtures). Keep `python -m pytest tests/` green at every step.

---

## Item 1 — `validate_all.py` + `Makefile` (right-sized orchestration)

**Why:** running the four validators by hand over a set is an error-prone manual dance. This is the "orchestration" the project needs — one command, consolidated report — **not** Airflow.

**Deliverable:** `scripts/validate_all.py`

```
python scripts/validate_all.py --set examples/<author>-set --skills-root examples
```

**Behavior:**
1. Load `<set>/set_manifest.json`; resolve each member's `skill_path`.
2. For each member skill, run (in-process, importing the functions — not subprocess):
   - `determinism_score.score_skill(chapters_dir)` → collect pct/counts.
   - `verify_concept_presence.verify_source(skill_dir)` → collect review_flags (skip gracefully if no `transcripts/`).
   - if a `coherence_audit.md` exists in the skill dir → `validate_coherence_audit.run_validation(...)`.
3. Run `validate_evolution_audit.run_validation(set_dir)` once for the set.
4. Print a consolidated table: per-skill determinism %, concept-presence flags, coherence pass/fail; then set-level evolution pass/fail.
5. **Exit code:** 0 only if every hard gate (coherence where present, evolution) passed. Determinism and concept-presence are informational (never fail the build — they are triage, per their design).

**Refactor prerequisite:** `determinism_score.py` currently only has a `__main__` block, no importable entry that takes a dir and returns the dict cleanly for reuse. It already has `score_skill(chapters_dir)` (`scripts/determinism_score.py:32`) — import that directly; no refactor needed. `verify_concept_presence.verify_source` and both validators' `run_validation` are already importable.

**`Makefile`** (repo root):
```makefile
test:            ; python -m pytest tests/ -q
validate-set:    ; python scripts/validate_all.py --set $(SET) --skills-root $(ROOT)
determinism:     ; python scripts/determinism_score.py $(SKILL)
```

**Tests:** `tests/test_validate_all.py` — build a 2-member mock set in a tempdir (reuse the fixture style from `tests/test_validate_evolution_audit.py::setup_mock_set`), assert exit 0 on a clean set and non-zero when the evolution audit is made to fail.

**Acceptance:** one command validates a whole set; consolidated report; correct exit code. Effort: **low**.

---

## Item 2 — `run.json` reproducibility record

**Why:** today there is no record of *what produced an artifact*. Model drift (review T1) and "can't reproduce a past doctrine" (W4) are real, but the proportionate fix is a **record**, not a model registry.

**Deliverable:** `scripts/write_run_manifest.py` + a `run.json` written into a set dir (or skill dir).

**`run.json` schema:**
```json
{
  "run_id": "2026-07-02T18-30-00Z",
  "generated_by_model": "claude-opus-4-8",        // filled by the human/operator
  "prompt_version": "git:<short-sha of SKILL.md>", // see below
  "sources": [
    {"source_id": "src1", "skill_path": "../skill-one",
     "source_sha256": "…", "artifacts_sha256": {"first_principles.md": "…", "sops.md": "…", "glossary.md": "…"}}
  ],
  "set_artifacts_sha256": {"<author>_evolution.md": "…", "<author>_current.md": "…"}
}
```

**Implementation:**
- `sha256_file(path)` and `sha256_dir_of(skill_dir, filenames)` helpers.
- `prompt_version`: capture `git rev-parse --short HEAD:SKILL.md` (blob sha of SKILL.md) via `subprocess`, fallback to `"unversioned"` if not a git repo.
- `generated_by_model`: accept `--model` arg (the operator passes what they used); default `"unspecified"`.
- Write `run.json` into the set dir.

**Integrate:** `validate_all.py --write-run` calls this after a successful validation so a passing set gets a stamped `run.json`.

**Tests:** hash a known file, assert stable digest; assert `run.json` has all sources and artifact hashes.

**Acceptance:** every published set carries a `run.json` you can diff against a later run to see exactly which source or artifact changed, under which model/prompt. Effort: **low**.

---

## Item 3 — JSON Schema for `set_manifest.json` + validator

**Why:** the manifest is the critical entry point; a malformed one currently fails deep inside the evolution validator with an opaque error (or silently skips members). Fail fast, clearly. (Review W5 / 5.5.)

**Deliverable:** `schemas/set_manifest.schema.json` (JSON Schema draft 2020-12) + `scripts/validate_manifest.py`.

**Schema rules to enforce:**
- `set_id`: string, required.
- `members`: non-empty array. Each member:
  - `source_id`: string matching `^[a-z0-9][a-z0-9_-]*$`, **unique across members**.
  - `date`: string matching `^\d{4}-\d{2}-\d{2}$`.
  - `role`: string (enum optional: `practitioner_book|primary_theory|live_training`).
  - `skill_path`: string, required.
  - `sequence`: integer, optional.
- Cross-field checks (beyond JSON Schema, in the validator):
  - `source_id` uniqueness.
  - every `skill_path` resolves to an existing directory relative to the manifest.
  - if any two members share a `date`, **all** members sharing that date must have `sequence` (mirrors the Chronology Gate tie-breaker in `validate_evolution_audit.py:117-133`).

**Dependency:** use `jsonschema` (add to dev deps). If avoiding the dep, hand-roll the checks — the ruleset is small; a dependency-free validator is acceptable and keeps install light.

**Integrate:** `validate_all.py` calls `validate_manifest` first and aborts with a clear message if it fails.

**Tests:** valid manifest passes; duplicate `source_id` fails; bad date format fails; tied dates without `sequence` fails; missing `skill_path` dir fails.

**Acceptance:** a broken manifest is rejected in <1s with a precise message naming the offending field. Effort: **low**.

---

## Item 4 — Structural provenance-integrity check

**Why:** `validate_evolution_audit.py` already checks the `_current.md` tag *format* (`scripts/validate_evolution_audit.py:96`, regex `\[[\w-]+/\d{4}…\]`) and does Jaccard claim-verification, but it does **not** check that the `source_id` inside each tag actually **exists in the manifest** with a **matching date**. A tag `[srcX/2025-01-01]` where `srcX` isn't a member, or where the date contradicts the manifest, passes today. This is the cheap structural half of the review's "attribution hallucination" concern (W11 / 2.9 / anti-hallucination gap "atribuição").

**Deliverable:** extend `validate_evolution_audit.py` with a `provenance_integrity` check (new function, wired into `run_validation`).

**Logic:**
- Parse every provenance tag in `<set>_current.md`: capture `source_id` and `date` from `[source_id/date, base: base_id/base_date]` (both the primary and the `base:` reference).
- For each captured `(source_id, date)`:
  - `source_id` must be a key in the manifest → else **FAIL** ("provenance tag cites unknown source 'srcX'").
  - `date` must equal the manifest date for that `source_id` → else **FAIL** ("tag date 2025-01-01 for src1 contradicts manifest 2019-01-01").
- This runs alongside the existing gates; hard-fail (return 1) on any mismatch.

**Tests:** add to `tests/test_validate_evolution_audit.py` — a `_current.md` citing an unknown source_id fails; a tag with a date mismatching the manifest fails; the existing valid fixtures still pass (guard against regression).

**Acceptance:** a provenance tag can no longer point at a source that isn't in the set, or lie about a source's date. Effort: **low**.

---

## Item 5 — Source checksums + change detection

**Why:** as sets grow to dozens of sources, re-running everything on every edit is wasteful, and there's no signal for "which source changed". Enables incremental work. (Review 5.7.)

**Deliverable:** builds on `run.json` (item 2). Add `scripts/detect_changes.py`.

**Behavior:**
```
python scripts/detect_changes.py --set examples/<author>-set
```
- Read the previous `run.json` in the set (if none, report "all sources new").
- For each member, recompute `source_sha256` (of the raw source if present) and `artifacts_sha256`.
- Print: `unchanged`, `source-changed` (raw source differs → needs re-extraction), `artifacts-changed` (extraction differs from last stamped run → needs re-audit).
- Exit 0 always (informational).

**Integrate:** `validate_all.py --since-last` prints the change summary at the top so the operator knows the minimal reprocessing set.

**Note on "raw source":** many skills won't have the raw source committed (that's the private-source convention — see `docs/ROADMAP.md` item 2). When absent, checksum only the artifacts and say so. Don't hard-require raw sources.

**Tests:** first run → all new; unchanged run → all unchanged; mutate one artifact → that member flagged.

**Acceptance:** before a re-run, the operator sees exactly which members need reprocessing instead of redoing the whole set. Effort: **low-medium**.

---

## Item 6 — Append-only run log (JSONL)

**Why:** no history today → can't see gradual degradation (determinism trending down, unverified-claim % creeping up). Proportionate observability = one JSONL file, not OpenTelemetry. (Review 2.6.)

**Deliverable:** `scripts/_runlog.py` with `append_run(record: dict, log_path="runs.jsonl")`, called by `validate_all.py`.

**Record per validation run:**
```json
{"ts": "2026-07-02T18:30:00Z", "set": "author-set", "evolution": "pass",
 "per_skill": {"skill-one": {"determinism_pct": 0.30, "concept_flags": 1, "coherence": "pass"}},
 "unverified_claims_pct": 0.10}
```
- Append one line per `validate_all` invocation to `runs.jsonl` at repo root (git-ignored — add `runs.jsonl` to `.gitignore`).
- Add a tiny reader: `python scripts/_runlog.py --tail 10` prints the last N runs as a table, and flags if `determinism_pct` dropped >0.1 vs. the previous run for the same skill, or `unverified_claims_pct` rose >0.1.

**Tests:** append two records, read back, assert the drop-detection fires on a synthetic regression.

**Acceptance:** `runs.jsonl` accumulates a trend you can eyeball; obvious regressions are flagged. Effort: **low**.

---

## Item 7 — Cross-model audit convention

**Why:** single-model dependency (review W3, but reframed): the real, cheap robustness win is running the **audit** sessions on a *different* model than the **extraction**. This is the one "ensemble" idea that pays for itself. Not multi-model consensus infrastructure.

**Deliverable:** documentation + a field, not a service.
- In `SKILL.md` Set-Level Workflows and the coherence handoff (Step 9.6), add a line: *"Run the isolated audit session on a different model family than the extraction where possible — a second model is less likely to rubber-stamp the first model's phrasing."*
- In `run.json` (item 2), add `audit_model` alongside `generated_by_model`, so the record shows whether extraction and audit used different models.

**Tests:** none (doc + schema field). Update the `run.json` test to assert `audit_model` is present.

**Acceptance:** the convention is documented and the run record captures it. Effort: **low (doc)**.

---

## Item 8 — Human-loop guardrails (conventions)

**Why:** the review's "infinite loop / no max retries / no final QA" concerns are real *as discipline*, not as code (there's no loop daemon). Make them explicit conventions. (Review W2 reframed, W12.)

**Deliverable:** a short `docs/OPERATING_CONVENTIONS.md`:
- **Re-run cap:** if an isolated audit fails its validator 3 times in a row, stop re-running and investigate the source/prompt — a persistent failure is a signal, not a retry candidate.
- **Final human QA gate:** before a set is considered "published", a human confirms `validate_all.py` is green **and** eyeballs `<set>_current.md` for completeness (the gates catch fabrication and contradiction, not *omission* — the one hallucination class no gate covers; review 4.2).
- **Model/prompt record:** never publish a set without a stamped `run.json` (item 2).

**Acceptance:** the operating discipline is written down where a new operator will find it. Effort: **low (doc)**.

---

## Item 9 — Domain synonym map (cheap paraphrase recall, no embeddings)

**Why:** `verify_concept_presence.py`'s salient-term matching and `validate_coherence_audit.py`'s Jaccard matching are both surface-token matchers — a faithful paraphrase using domain synonyms ("range" vs. "banda de preço", "colidiu" vs. "bateu") reads as absent/unverified even when the claim is correct. This is real (the calibration note in `verify_concept_presence.py:34-44` already found one faithful-but-heavily-paraphrased principle at 20%). The alternative — sentence embeddings/NLI (Phase 2 below) — solves this plus semantic entailment, but at the cost of a heavy model dependency. A **per-domain synonym map** solves the paraphrase-recall half of that gap for near-zero cost, staying pure-Python, human-auditable, and cumulative as you add more authors in the same field (the stated near-term case: a second author in the same market-structure domain as the existing Set).

**Explicitly out of scope for this item:** semantic entailment / negation detection ("never do X" vs. "do X") — a static synonym list cannot catch that; it stays a Phase 2 (or human-audit) concern. Item 9 only widens *recall* for correct-but-differently-worded claims; it does not add a new correctness gate.

**Deliverable:**
1. `schemas/domain_synonyms.schema.json` — same lightweight-contract pattern as `set_manifest.schema.json` (Item 3): documents the expected shape, not a runtime dependency.
2. `domains/<domain-id>/synonyms.json` — one file per subject area (e.g. `domains/market-structure/synonyms.json`), format:
   ```json
   {
     "domain_id": "market-structure",
     "groups": [
       {"canonical": "range", "synonyms": ["banda de preço", "faixa de preço", "bounded area"]},
       {"canonical": "initiative", "synonyms": ["directional conviction", "aggressive participation"]}
     ]
   }
   ```
3. `scripts/domain_synonyms.py`:
   - `load_domain_synonyms(domain_id: str) -> dict[str, str]` — loads `domains/<domain_id>/synonyms.json` and returns a flat `{synonym_token: canonical_token}` lookup (lowercased, hyphen/slash-split consistent with `verify_concept_presence.salient_terms`).
   - `normalize_terms(terms: list, synonym_map: dict) -> list` — maps each term to its canonical form when present in the map, passes through unchanged otherwise. Pure function, no I/O.
4. **Wiring into `verify_concept_presence.py`:** `score_principle()` gets an optional `synonym_map` parameter; when present, both the claim's `salient_terms()` output and the corpus text are normalized through `normalize_terms()` before the presence check. Default `None` — behavior is unchanged unless a domain is explicitly passed, so existing calibration (the `REVIEW_FLOOR = 0.34`) isn't invalidated for sources that don't use one.
5. **Wiring into `validate_coherence_audit.py`:** same optional-parameter pattern for `verify_claim()` — normalize both `claim` and `source_text` tokens before Jaccard, when a `synonym_map` is supplied.
6. **CLI:** `verify_concept_presence.py --domain market-structure path/to/skill` and `validate_all.py --domain market-structure <dir>` (passed through to both checks when `domains/<domain>/synonyms.json` exists; silently skipped otherwise — no domain, no behavior change).
7. **Population workflow (human-in-the-loop, not automated):** after extracting a source, an operator may ask the extraction LLM to propose synonym candidates from that source's own `glossary.md` (one-off prompt, not a pipeline step); a human reviews and merges accepted pairs into the domain's `synonyms.json`. The file is committed and versioned like any other input — it is data, not inferred at runtime.

**Tests (`tests/test_domain_synonyms.py`):**
- `load_domain_synonyms` returns the expected flat map for a fixture file; missing domain file → empty dict (no crash).
- `normalize_terms` maps known synonyms to canonical form and passes unknown terms through unchanged.
- `score_principle(..., synonym_map=...)` turns a previously-absent synonym term present via its canonical form (regression test replicating the "banda de preço" vs. "range" case).
- `verify_claim(..., synonym_map=...)` raises a previously-failing Jaccard match to pass when the only difference is a mapped synonym.
- No-domain-passed path is byte-identical to current behavior (guards against silently changing scores for sources that don't opt in).

**Acceptance:** existing 218 tests still pass unchanged (no default-path behavior change); new tests pass; running the concept-presence triage on a synthetic paraphrase-heavy fixture shows a measurable score increase only when `--domain` is passed. Effort: **low-medium** (pure Python, no new dependency; the human curation step is out-of-repo work, not code).

---

## Item 10 — Extraction pre-flight scan + checklist (config-answer review)

**Why:** `SKILL.md` Steps 1.5, 4, 5, and 5.5 are written as a live back-and-forth with a human, but in practice an operator (or an executor acting on their behalf) pre-answers all of them in a single "Full Conversion" prompt so the run can proceed unattended. Nothing today forces a review of those pre-answers *before* extraction starts — and a wrong answer to Step 1.5 in particular is expensive to discover after the fact: a source whose core argument is carried by tables/diagrams, pre-configured as `BOOK_TYPE=text`, silently loses that content to a plain-text extractor, often undetected until a human reads the generated chapters closely. This project is domain-agnostic and this failure mode is too — it can happen to any source in any field, so the mitigation must not assume or reference any specific book, author, or subject.

**Deliverable, two parts:**

1. **`scripts/preflight_scan.py`** — an automated, dependency-light scanner (reuses the `pypdf` optional dependency already declared in `pyproject.toml`'s `pdf` extra; degrades gracefully if it isn't installed). For a PDF source, it samples pages spread evenly across the *whole* document (not just the front, where content-type is least representative), and for each sampled page measures (a) presence of embedded images and (b) a tabular-line-layout heuristic (repeated multi-space-separated tokens/numeric rows). From these it emits a `BOOK_TYPE` suggestion with a confidence level (`high`/`medium`/`low`) and explicit warnings when signal is weak or images are present — always framed as a suggestion for human confirmation, never an automatic decision. Non-PDF sources (epub/docx/txt/md) are not page-sampled (lower risk profile from their extractors) and get a low-confidence default plus a prompt to judge by hand.
2. **`docs/EXTRACTION_PREFLIGHT_CHECKLIST.md`** — a short, subject-agnostic template the operator fills in and re-reads *before* handing a "pre-answered Full Conversion" prompt to an executor, covering:
   - **Step 1.5 (`BOOK_TYPE`):** run the scanner first; then confirm whether the source's *core argument* — not incidental illustration — is carried by a table, chart, formula, or diagram. If yes, `BOOK_TYPE=technical` regardless of how prose-heavy the rest of the source reads or what the scanner suggested at low/medium confidence. Note whether flagged figures are selectable text or rasterized images — if rasterized, document upfront that no `BOOK_TYPE` recovers them, so the gap is expected rather than discovered after a full run.
   - **Step 4 (`DEPTH`):** confirm the stated purpose actually maps to the intended token budget (option 3-only → `reference`; anything else → `study`).
   - **Step 5 (name/destination):** if the destination skill directory already exists, confirm "overwrite" is really intended (vs. Update/Fold-in or Rename).
   - **Step 5.5 (lineage):** author-name auto-detection only catches same-author lineages; a deliberate cross-author grouping (an originating work feeding later authors' extensions in the same field) is never auto-suggested and must be decided explicitly, in writing.

**Tests (`tests/test_preflight_scan.py`):** pure-function coverage of the sampling spread, the tabular-line heuristic (prose vs. tabular-data fixtures), and the suggestion/confidence logic — no real PDF fixture required. Also covers the graceful-degradation path when `pypdf` is unavailable.

**Acceptance:** `preflight_scan.py` runs standalone against a PDF and against a non-PDF path without crashing either way; the checklist is linked from `SKILL.md`'s Step 1.5 section and from `docs/OPERATING_CONVENTIONS.md`; the convention is that no pre-answered Full Conversion prompt is handed off without both the scan and the checklist. Effort: **low** (reuses an existing optional dependency; no new one added).

---

## Item 11 — Architecture Reverse-Engineering Audit — "Blackhat Mode" (a sibling of the evolution audit)

> **Blackhat Mode** is the product name for this layer — the opt-in mode that turns the pipeline from a faithful transcriber into a disciplined reverse-engineer of a demonstrated system. The name is branding; the discipline below (seals, gates, evidence-grounded inference) is what makes it honest rather than a jargon-dressed guess.

**Why:** the extraction core is valuable *because* of the anti-fabrication rule — it only records decision-logic the author explicitly stated, and marks everything uncertain as a Heuristic. But there is a legitimate, recurring task the core deliberately does **not** serve: given source material that *demonstrates a system* (a screen-recorded walkthrough of a proprietary tool, an algorithmic decision-support product, a workflow shown but not fully explained), reconstruct a hypothesis of how the system works internally — deduce the backend from the observable frontend. That is **inference about what the author did not reveal**, which is the epistemic opposite of faithful extraction. Bolting it into the extraction engine would destroy the guarantee that a line in `SKILL.md` is something the author actually said. So it must live *outside* the core, as a new deterministic-validation layer that **consumes** an already-extracted skill and never writes back into it — architecturally a sibling of the coherence audit and the temporal evolution audit, not a change to extraction.

**The two decisions this item turns on (candidacy vs. intent):**

1. **Candidacy is detectable from the material; intent is not.** Whether a source is *a candidate* for reverse-engineering — "does this describe a system with an observable frontend?" — is a content property the pre-flight scanner can flag (signals: on-screen UI references — "look at this", "olha aqui", "click on" — a named proprietary system, outputs/signals displayed without the computation that produced them, dashboards/charts shown as objects rather than explained). Whether the operator *wants* faithful doctrine or *wants* to reconstruct the hidden backend is a **goal**, not a property of the bytes: the identical video serves "I want to operate this method" and "I want to deduce how the engine works." The material cannot tell them apart.
2. **Therefore the RE mode is detected-and-suggested, never auto-activated.** Following the Item 10 pattern, the scanner *detects candidacy and recommends*, and mode selection is a one-key approve — the operator never writes a briefing from scratch. But the RE layer is **only** ever activated by an explicit operator declaration, even when the material is a 100% candidate, because (a) inferring someone's proprietary backend is speculative by nature and turning it on unasked is the inverse of the core's anti-fabrication discipline, and (b) the declaration is recorded in the artifact (`intent: reverse-engineering, approved by <operator>`) so it is auditable *who* requested the inference.

**Deliverable, four parts:**

1. **Scanner candidacy signal (`scripts/preflight_scan.py` extension).** Add a `system_demonstration` detector to the existing scan: count on-screen/UI-deixis references, detect a named-system pattern, and flag "outputs shown without their computation." Emit an `re_candidate: true/false` field with the signal breakdown, and — when true — surface a two-option prompt in `--emit-prompt` output: `[A] faithful doctrine only (normal audit → SKILL.md)` vs `[B] Blackhat Mode: faithful doctrine + reverse-engineering layer (adds <sys>_architecture.md)`. `[A]` remains the default; `[B]` is never pre-selected.

2. **Analyst-lens derivation (the third pre-flight field, next to `BOOK_TYPE` and `re_candidate`).** A generic point of view produces a shallow reverse-engineering parecer — to speculate with density about a backend, the inference pass must reason *as a domain expert* (recognize that an on-screen chart is a volume profile, that a displayed number is an execution signal), not as a generic viewer who cannot even label what is shown. This expertise is **not hardcoded per domain** (that would break agnosticism — anyone can bring any technical course): it is **derived from the material and confirmed at pre-flight**, the same detect-and-suggest one-key flow as `BOOK_TYPE`. The scanner infers a candidate field from signals it already has — the named system, the source's own vocabulary, the generated `glossary.md`, the Item 9 domain synonym map — and proposes an `analyst_lens` (e.g. *"quantitative-systems-architect"*); the operator confirms or overrides one-key, never writing it from scratch. The confirmed lens is (a) injected into the RE inference prompt as the analytical persona and (b) recorded in the artifact front-matter (`analyst_lens: <slug>`), so it is auditable *which expertise POV* produced the pareceres. **Guardrail (critical):** the lens sharpens *what is recognized and which questions are asked* — it never relaxes *whether an inference needs evidence*. A domain expert "filling in" the backend they'd expect is precisely the fabrication risk this whole item exists to prevent; the Grounding Gate below applies identically regardless of persona.

3. **The architecture artifact + its provenance grammar (`<system>_architecture.md`).** Produced by an isolated LLM pass (like the coherence audit — a human running an agent in a fresh session, *not* programmatic), consuming the already-extracted skill's `first_principles.md`, `sops.md`, `chapters/`, and any rescued `frames/`. Every line carries exactly one of two seals:
   - `[OBSERVED src/12:34]` — a fact the author showed or stated, traceable to a source location (the same provenance tag grammar the rest of the pipeline uses).
   - `[INFERRED ← obs A + obs B]` — a hypothesis about internal mechanism, which **must** cite the observed evidence it rests on.
   The artifact is written *alongside* the skill and is never merged into `SKILL.md` — the observed/inferred boundary is the whole point and must stay visibly separate from the faithful doctrine.

4. **The validator (`scripts/validate_architecture_audit.py`) — deterministic, no LLM.** Mirrors `validate_evolution_audit.py`'s gate structure:
   - **Seal Gate:** every non-heading, non-blank claim line carries exactly one seal (`[OBSERVED …]` or `[INFERRED …]`) — an unsealed assertion fails the build (the equivalent of a missing provenance tag).
   - **Grounding Gate** (the RE analogue of Claim Verification): every `[INFERRED ← …]` must reference at least one `[OBSERVED …]` claim that exists elsewhere in the same artifact — an inference with no observed support fails. This gate is **persona-blind**: it applies identically no matter what `analyst_lens` produced the line, which is exactly what stops an expert lens from licensing "backend I'd expect" fabrication — a densely-argued inference with no cited observation fails the same as a naive one.
   - **Non-Contamination Gate:** the audit fails if `SKILL.md` / `first_principles.md` / `sops.md` contain any `[INFERRED …]` seal — inference must never have leaked back into the faithful core.
   - **Intent Gate:** the artifact's front-matter records `intent: reverse-engineering`, an approver, and the confirmed `analyst_lens`; any missing → fail (the artifact cannot exist without a recorded human authorization *and* a recorded analytical POV).

**Tests (`tests/test_validate_architecture_audit.py` + additions to `tests/test_preflight_scan.py`):** pure-function coverage of each gate (a fixture artifact that passes all four; one variant per gate that trips exactly that gate: an unsealed line, an `[INFERRED]` with no matching `[OBSERVED]`, an `[INFERRED]` seal planted in `first_principles.md`, missing intent front-matter, and — separately — missing `analyst_lens` front-matter tripping the Intent Gate). Scanner-side: a transcript fixture with UI-deixis + named-system signals yields `re_candidate: true` and a proposed `analyst_lens` derived from its vocabulary; a pure-conceptual-theory transcript yields `re_candidate: false`; `--emit-prompt` on a candidate offers `[A]/[B]` with `[A]` default and surfaces the proposed lens for one-key confirm/override.

**Acceptance:** the validator runs standalone against an `<system>_architecture.md` and passes/fails deterministically on the fixtures; the four gates are documented in the README audit-apparatus table as a fourth layer; the scanner's `re_candidate` flag, the `analyst_lens` derivation, and the `[A]/[B]` selection are documented in `docs/EXTRACTION_PREFLIGHT_CHECKLIST.md`; nothing in the extraction core changes (the core stays anti-fabrication-pure, and the Non-Contamination Gate enforces that mechanically). Effort: **medium** (the validator and scanner signal are pure-Python and testable; the hypothesis-generation pass is an out-of-repo human+agent step, exactly like the coherence and evolution audits, not pipeline code).

---

## Item 12 — Unified CLI menu (single entrypoint + frontend scaffolding)

**Why:** the toolkit is ~14 loose scripts in `scripts/` plus one packaged entrypoint (`book-to-skill`). A newcomer who opens the project at the CLI has no single door that answers "what can this tool do?" — they have to read the README, learn each script's flags, and remember the right order (scan → extract → validate → audit). A single interactive menu makes the whole surface discoverable in one command, and — built correctly — doubles as the **contract a future web frontend maps onto 1:1**: every menu item is a capability that already exists, so a GUI later is a re-skinning of the same dispatch, not a rewrite of logic.

**The one rule that makes this scaffolding instead of tech debt:** the menu is a **thin dispatcher over the scripts that already exist — it contains no new domain logic.** Each menu item shells out to (or imports and calls the `main()` of) an existing script with the same arguments a user would pass by hand. If a menu item needs logic that isn't already in a script, that logic belongs in the script (reusable, testable) first, and the menu only calls it. This keeps the menu trivially thin, keeps every capability usable head-less (scriptable/CI) *and* interactively, and guarantees the future frontend consumes the same underlying scripts through the same interface.

**Deliverable:**

1. **`scripts/menu.py` + a `sopx` console-script entry** (added to `pyproject.toml`'s `[project.scripts]` alongside the existing `book-to-skill`). Running `sopx` with no arguments prints the banner (`scripts/banner.txt` already exists) and an interactive numbered menu; running `sopx <verb> [args]` (e.g. `sopx scan <path>`) dispatches directly without the menu, so the menu is a convenience layer, never the only way in.
2. **Menu map (each item = one existing capability, and one future frontend route):**
   - `1) Scan a source` → `preflight_scan.py` (offers `--emit-prompt`)
   - `2) Extract a skill` → prints the approved prompt and the `SKILL.md` hand-off instructions (the extraction itself is the agent's job, not the menu's — the menu never pretends to run the LLM pass)
   - `3) Validate a skill` → `validate_all.py`
   - `4) Audits` → submenu: `a` coherence (`validate_coherence_audit.py`), `b` evolution (`validate_evolution_audit.py`), `c` **Blackhat / reverse-engineering** (`validate_architecture_audit.py`, Item 11 — shown as "coming soon" until Item 11 ships, never a dead option that errors)
   - `5) Determinism score` → `determinism_score.py`
   - `6) Summary / run log` → `extraction_summary.py` + `_runlog.py`
   - `q) quit`
3. **Discovery-driven, not hardcoded where possible:** the menu resolves each script by the same path-search convention `SKILL.md` Step 2 already uses (so it works from any of the supported skill roots), and greys out (with a one-line reason) any capability whose backing script or optional dependency is absent — the menu is honest about what the current install can actually do, mirroring `extract.py --check`.

**Tests (`tests/test_menu.py`):** pure-function coverage of the dispatch table (verb → script mapping), the "coming soon" state for a not-yet-built capability (Item 11 before it ships), and the graceful greying-out when a backing script/dependency is missing — driven by injecting a fake capability registry, no subprocess spawning required. The interactive loop itself is a thin `input()`/dispatch shell exercised with a scripted input sequence.

**Acceptance:** `sopx` with no args shows the menu and every listed item either runs its script or explains why it can't; `sopx scan <path>` works head-less identically to `python scripts/preflight_scan.py <path>`; the menu adds no capability that isn't already a standalone script; README's Usage section gains a one-line "or just run `sopx`" pointer above the numbered flow. Effort: **low-medium** (pure dispatch + argument pass-through; the capabilities already exist and stay independently runnable).

**Frontend note (why this is the arcabouço):** when/if a web or desktop frontend is built, the menu map above *is* the route map — upload+scan (item 1), extract hand-off (item 2), validate (item 3), the audit tabs (item 4), etc. Because every item is a thin call over an existing deterministic script, the frontend and the CLI share one backend surface; nothing in the pipeline needs a second implementation to become a product.

---

## Item 13 — Audit findings (backend/frontend/UX, world-class-KM gap analysis)

**Why:** an end-to-end run against real material (two ASG course videos, Items 11/12's own validation) surfaced a real-world failure mode: the executor skipped Step 7.5 (frame rescue) citing "1.6GB", which turned out to be a misread of "1,600 snapshots/second" mentioned in the transcript — not a real cost. Nothing in the pipeline caught that a step was skipped for a fabricated reason. That incident, plus a broader audit of the project as a knowledge-management tool, surfaces four gaps that are all **thin-shell fixes over what already exists** — no new subsystem, no framework, no "perfumaria." Ranked by impact/effort, in build order.

**Explicitly out of scope (perfumaria at this scale, confirmed against the existing "Out of scope" table):** a full web/SaaS frontend, vector DB/RAG/knowledge graph, multi-user/RBAC/auth, an orchestrator. The static HTML viewer below (13.4) delivers the visual-surface value at a fraction of that cost; build the rest only when real users ask for it.

### 13.1 — `sopx` unified CLI (implements Item 12)

Item 12 above is the spec; this sub-item is the acceptance trigger: build it now, first, because every other Item 13 gap either depends on it (13.4's viewer reuses its dispatch map) or is made discoverable by it. Deliverable and acceptance are exactly Item 12's — no re-spec needed here.

### 13.2 — Scanner↔extractor format contract (prevents the `.srt` class of bug)

**Why:** the `.srt`/`.vtt` bug fixed this week (PRs #5, #6, #7) happened because `preflight_scan.py`'s supported-format set and the `book_to_skill` package's `SUPPORTED_EXTENSIONS` were two independent, hand-maintained lists that silently drifted — the scanner correctly recommended `BOOK_TYPE=transcript` for a format the extractor rejected outright. Nothing enforced that the two stay in sync; the gap was found by running the real pipeline, not by any test.

**Deliverable:**
1. A single source of truth for "formats this tool has real scanning + real extraction for" — e.g. `scripts/format_registry.py` exporting `SCANNED_EXTENSIONS` (what `preflight_scan.py` samples with real signal) and re-exporting/importing `book_to_skill.config.SUPPORTED_EXTENSIONS` (what `extract.py` can actually parse) so both sides read from one place instead of hand-copied literals.
2. A parity test (`tests/test_format_parity.py`) that fails the build if `SCANNED_EXTENSIONS` ever contains a format `SUPPORTED_EXTENSIONS` doesn't (a scanner claiming to recommend a format the extractor can't touch) — the direction that actually bit us. The reverse (extractor supports a format the scanner doesn't sample, e.g. epub/docx today) is allowed and already documented as a low-confidence default, not a bug.

**Tests:** the parity test itself, plus a regression test asserting `.srt`/`.vtt` are in both sets (guards this exact incident from silently recurring if either list is edited independently in the future).

**Acceptance:** `pytest tests/test_format_parity.py` fails on a synthetic drift (temporarily removing `.srt` from one list, restored after assertion) and passes on the current, in-sync state. Effort: **low** (one small registry module + one test file; no behavior change to either script).

### 13.3 — `run_report.json` + skipped-step gate (observability of what the executor actually did)

**Why:** the "1.6GB" incident is a specific instance of a general gap: nothing in this pipeline records *which* `SKILL.md` steps ran, which were skipped, and why. An operator reviewing a finished skill has no artifact to check "was Step 7.5 really skipped for a real cost reason, or a hallucinated one?" — they'd have to re-read the whole agent transcript by hand, if they even kept it.

**Deliverable:**
1. `SKILL.md` gains an explicit convention: at the end of a run, the executor writes `run_report.json` into the skill directory, listing every numbered step (0–9, 7.5 when applicable) with `status: ran|skipped` and, for any `skipped`, a mandatory non-empty `reason` string.
2. `scripts/validate_run_report.py` — a deterministic, no-LLM checker: fails if `run_report.json` is missing, if any step is missing from it, or if any `skipped` step has an empty/placeholder reason. It does **not** attempt to judge whether the reason is *true* (that requires re-verifying against the source, out of scope for a mechanical gate) — it only enforces that a reason was recorded, which is what would have made "1.6GB" for a 60MB file visible for human review instead of silently accepted.
3. Wired into `validate_all.py` as one more check in the consolidated report (informational by default — matching the project's existing "hard gate vs. triage" split for determinism/concept-presence; promote to hard-fail only if the team decides skipped-without-reason should block).

**Tests:** `tests/test_validate_run_report.py` — missing file, missing step, empty reason (each trips the check); a complete, honest report passes.

**Acceptance:** running `validate_all.py` against a skill with a `run_report.json` missing a reason for a skipped step surfaces it in the consolidated output; against a complete one, it's silent. Effort: **low-medium** (one small script, one convention line in `SKILL.md`, one test file).

### 13.4 — Static HTML viewer for a generated skill (output becomes a product, not six `.md` files)

**Why:** a generated skill's real content — provenance tags, `[OBSERVED]`/`[INFERRED]` seals, determinism %, chapter structure — is currently only readable by opening six separate Markdown files in an editor. That is the single biggest UX gap between "personal notes" and "a knowledge-management product," and it's the one Item 12's menu map was explicitly designed to scaffold toward.

**Deliverable:** `scripts/render_skill_viewer.py` — takes a skill directory and renders **one self-contained HTML file** (inline CSS/JS, no server, no build step) with:
- a left nav listing `SKILL.md` sections + `chapters/*` + `<system>_architecture.md` if present,
- provenance tags (`[src/date]`) and, where present, `[OBSERVED]`/`[INFERRED]` seals rendered as distinct colored badges (never re-styled to look identical — the visual distinction is the point),
- the determinism-score % and gate pass/fail badges from `validate_all.py`'s output, if a prior run's result is available in the skill dir.

This reuses Item 12's `sopx` dispatch map directly (`sopx view <skill_dir>` is a thin call to this script) rather than inventing a second interface.

**Tests:** `tests/test_render_skill_viewer.py` — a synthetic skill dir with a `SKILL.md`, one chapter, and an `<system>_architecture.md` containing both seal types renders one HTML file containing the expected nav entries and both badge classes; missing optional files (no architecture doc) render without error, just without that nav entry.

**Acceptance:** `sopx view path/to/skill` opens (prints the path to) a single HTML file that a human can read start-to-finish without touching a terminal again, with OBSERVED/INFERRED visually distinguishable at a glance. Effort: **medium** (templating + one Python script; no dependency — stdlib string templating, no Jinja2 needed at this scale).

**Deferred (Phase 2, not this item):** semantic claim verification (already speced in Phase 2 above) and a `sopx init` one-command quickstart — both real, both lower priority than closing the four gaps above, which each fix or would have caught a concrete failure mode observed in production use this week.

---

## Item 14 — Multi-part-course practical blind spots (merge tool + batch scan)

**Why:** processing the two real ASG videos end-to-end this week surfaced two concrete, repeatable friction points that Items 11-13 didn't cover, because they only showed up when actually running a multi-part course through the pipeline as two separate extractions:

1. **No tool to consolidate per-part Blackhat artifacts.** Each part produced its own `<system>_architecture.md` with its own `O1`/`I1` numbering starting from scratch. Getting one coherent picture meant manually renumbering ids across files, re-pointing `INFERRED` citations at the new ids, and re-validating the four gates by hand — real, repeatable, mechanical labor with zero domain judgment in it (the domain judgment — spotting that vid1's histogram and vid2's CVD hypothesis are the same mechanism — is a separate, legitimate human/agent synthesis step this item does *not* try to automate).
2. **No batch entrypoint for multi-part courses.** Scanning N parts of one course meant running `preflight_scan.py` once per file and manually deciding/declaring fold-in vs. isolated and stitching N separate prompts by hand, instead of one command that treats them as one course from the start.

**Deliverable, two parts:**

1. **`scripts/merge_architecture_audit.py`** — merges N per-source architecture artifacts into one. Renumbers `O`/`I` ids continuously across sources (first-occurrence-order, per source, mapped through a per-file id table), rewrites `INFERRED` citations to point at the renumbered ids, pools `## Frontend observations` and `## Inferred backend` bullets from all sources under one heading each (not interleaved by source), and preserves any other per-source prose (e.g. `## Confidence & gaps`) under a `## Per-source notes` section tagged by originating filename — no per-source nuance is discarded. Front matter is merged: `intent` must be `reverse-engineering` on every source; `approved_by` is unioned (or overridden via `--approved-by`); `analyst_lens`/`system` are kept from the first source, with any differing values from later sources surfaced as `analyst_lens_variants`/`system_variants` rather than silently dropped. The merged artifact is re-validated against the same Intent/Seal/Grounding gates `validate_architecture_audit.py` enforces (Non-Contamination needs a skill dir the merge step doesn't have context for, so it's out of scope here — run it separately against the final skill dir).
2. **Batch dispatch in `scripts/preflight_scan.py`** — `source_path` becomes `nargs='+'`; a single path behaves exactly as before (no regression), multiple paths trigger `scan_batch()` (scans each, in order) and, with `--emit-prompt`, `build_multi_part_prompt_draft()` — one prompt covering all parts as `PART_ID=part1..partN` (matching `SKILL.md`'s existing multi-part convention), warning if parts disagree on `BOOK_TYPE`, and — when any part is an RE-candidate — pointing at `merge_architecture_audit.py` as the next step after per-part extraction.

Both wired into `sopx`: `scan` already accepted pass-through args, so `sopx scan part1.srt part2.srt --emit-prompt` works unchanged; a new `merge-arch` capability added to the menu.

**Tests:** `tests/test_merge_architecture_audit.py` (continuous renumbering across two realistic sources shaped exactly like the real vid1/vid2 artifacts, section pooling not interleaving, per-source prose preservation, front-matter merge/variant-flagging, `--approved-by` override, and — critically — the merged output re-validated with the real `validate_architecture_audit.run_validation`, not just the merge script's own gate calls); `tests/test_preflight_scan.py` additions for `scan_batch` and `build_multi_part_prompt_draft` (part listing, disagreement warning, merge-tool pointer only when RE-candidate).

**Acceptance:** `python scripts/merge_architecture_audit.py part1_architecture.md part2_architecture.md --out <system>_architecture.md` produces a single artifact that passes `validate_architecture_audit.py` standalone; `sopx scan part1.srt part2.srt --emit-prompt` emits one multi-part prompt instead of requiring two separate manual runs. Effort: **low** (both reuse existing parsing/regex/gate code; no new dependency, no new gate).

---

## Phase 2 (after the Pareto 8 — highest-value non-Pareto item)

**Semantic claim verification.** The deepest real anti-hallucination gap the review found (4.2 "paráfrase distorcida", Claim Verification "verificação estrutural, não semântica"): today `validate_evolution_audit` / `validate_coherence_audit` verify claims via Jaccard token overlap (`scripts/validate_coherence_audit.py:verify_claim`), which a subtly-distorted paraphrase can pass. Upgrade path, keeping it dependency-light:
1. Keep Jaccard as the cheap first pass.
2. Add an optional second pass: sentence-embedding cosine similarity between claim and best-matching source sentence, with a threshold; or an NLI entailment check if a small model is available locally.
3. Gate on: Jaccard-pass **or** embedding-pass (union), and flag "Jaccard-fail but embedding-pass" rows for human review (they're the paraphrase cases).
Effort: **medium**. Deferred out of the Pareto because it needs a model/embedding dependency and calibration, unlike items 1-8 which are pure-Python and instant.

---

## Out of scope (and why) — do NOT build these

| Review recommendation | Why rejected at this scale |
|---|---|
| Airflow/Prefect/Dagster orchestrator | `validate_all.py` + Makefile is the right size for a human-run toolkit on dozens of sources. |
| Vector DB / semantic search / RAG index | Solves consumption-at-scale; not the compiler's job. Out of scope until there's a query product. |
| Knowledge graph / OWL/RDF ontology | High effort, no payoff below hundreds of interlinked sources. |
| K8s worker pool / Kafka / map-reduce | Enterprise throughput for thousands of sources — explicitly excluded. |
| RBAC / approval workflow / digital signatures / GDPR-LGPD / PII | Enterprise governance/compliance; not a personal/small-team tool's concern. |
| Multi-model consensus / judge ensemble | Item 7 keeps the cheap 80% (different model for audit) without the voting infrastructure. |
| Circuit breaker / max_retries as code | No automated loop exists; handled as convention in item 8. |

**Rationale in one line:** the review conflates *maturity* with *enterprise size*. Items 1-8 buy maturity (reproducibility, fail-fast, trend visibility, integrity) at near-zero cost; everything above buys size the project doesn't need.

---

## Suggested execution order

1 → 3 → 4 → 2 → 6 → 5 → 7 → 8 → 9, then Phase 2.

(1 gives the harness everything else plugs into; 3 and 4 are the highest-integrity-per-hour; 2 and 6 add the reproducibility/trend spine; 5 depends on 2; 7 and 8 are doc-weight finishers; 9 is independent of 1-8 and can be pulled forward whenever a second author in the same domain makes paraphrase recall worth curating.)

Keep `python -m pytest tests/` green after each item; each item ships with its own tests.
