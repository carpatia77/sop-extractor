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

## Item 10 — Extraction pre-flight checklist (config-answer review, human convention)

**Why:** `SKILL.md` Steps 1.5, 4, 5, and 5.5 are written as a live back-and-forth with a human, but in practice an operator (or an executor acting on their behalf) pre-answers all of them in a single "Full Conversion" prompt so the run can proceed unattended. Nothing today forces a review of those pre-answers *before* extraction starts — and the wrong answer to Step 1.5 in particular is expensive to discover after the fact. This is not hypothetical: the Steidlmayer extraction was pre-configured with `BOOK_TYPE=text` (Option 2, "text-heavy... few or no tables"), when the source is a Market Profile book whose central content is TPO charts — tabular/diagrammatic material that `text` mode's `pdftotext` extractor does not preserve. It was only caught because the operator happened to show a screenshot of one such chart in conversation; nothing in the pipeline would have flagged the mismatch on its own, and running with `BOOK_TYPE=technical` (Docling) from the start would have given the extraction the best chance of recovering the tabular content that was recoverable (the two tables it did rescue in ch06 came from choosing correctly, after the fact).

**Deliverable:** `docs/EXTRACTION_PREFLIGHT_CHECKLIST.md` — a short template the operator fills in and re-reads *before* handing a "pre-answered Full Conversion" prompt to an executor (human or agent), covering:
- **Step 1.5 (`BOOK_TYPE`) sanity check:** open the source and sample 3-5 pages spread across it (not just the first chapter). Is any of the book's *core argument* — not incidental illustration — carried in a table, chart, formula, or diagram? If yes, `BOOK_TYPE=technical` regardless of how prose-heavy the rest of the book reads; "text-heavy" is about the book's *dominant* content, not its majority page count. Note whether those figures are selectable text or rasterized images — if rasterized, flag upfront (in the eventual `SKILL.md`/glossary) that they will not survive extraction under *any* `BOOK_TYPE`, so the gap is expected and documented from the start rather than discovered after a full run.
- **Step 4 (`DEPTH`) sanity check:** confirm the stated purpose actually maps to the intended token budget (option 3-only → `reference`; anything else → `study`) — this one is mechanical and rarely wrong, but a one-line confirmation costs nothing.
- **Step 5 (name/destination) sanity check:** if the destination skill directory already exists, confirm that "overwrite" is really intended (vs. Update/Fold-in or Rename) — a pre-answered "overwrite" in a batch prompt can silently destroy a prior extraction the operator forgot was there.
- **Step 5.5 (lineage) sanity check:** author-name auto-detection only catches same-author lineages. A deliberate cross-author "school of thought" grouping (e.g. Steidlmayer as `primary_theory` originator feeding into the Dalton Set as `practitioner_book` extensions) will never be auto-suggested — the operator must decide this explicitly, in writing, before the run, rather than defaulting to "isolated extraction" by omission.

**Acceptance:** the checklist file exists, is linked from `SKILL.md`'s Step 1.5 section and from `docs/OPERATING_CONVENTIONS.md` (Item 8), and the stated convention is that no pre-answered Full Conversion prompt is handed off without the checklist being filled in first. This is a discipline, not a gate a script can enforce — same category as Item 8. Effort: **low (doc)**.

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
