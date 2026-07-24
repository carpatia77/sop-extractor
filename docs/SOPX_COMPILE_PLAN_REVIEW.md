# Review — `SOPX_COMPILE_PLAN.md`

**Reviewer:** engineering audit
**Verdict:** solid plan; one architectural change collapses the critical-path
blocker and removes a security footgun, plus five hardening points — the fifth
(§2.5) added after a follow-up discussion and made a **hard MVP requirement**,
not a nice-to-have. The hard part isn't the LLM call — it's parse robustness,
mandatory grounding, stamped provenance, and a real human checkpoint at batch
scale.

---

## 1. The big one: close the hand-off via the agent CLI, not a direct-API caller

The plan puts **Phase 3 (direct LLM API call)** on the critical path and names the
unbuilt **LLM Router** as the blocking dependency. Going direct to an API
reintroduces exactly what this project deliberately avoided: `menu.py` marks the
`extract` capability `info_only` — *"the menu never pretends to run the LLM
pass."* That's a design stance, not a gap. The project **delegates** the LLM step
to the agent (Claude / Copilot / Amp) the user already has authenticated.

**Promote the plan's own option 3 (subprocess to the agent CLI) from "interim" to
primary.** Rationale:

- **No API-key management** → removes the plaintext-secret risk the plan itself
  rates "Critical". The user is already authenticated in `claude`/`copilot`/`amp`.
- **No Router, no cost-tracking, no BYOK** → the "blocking dependency" disappears.
  The gap closes with ~one subprocess call, not three new modules + a router.
- **Provider-agnostic by construction** → a `--agent claude|copilot|amp` flag
  mirroring the existing `validate_skill.py --lens claude|copilot|amp`.
- **Keeps the determinism boundary honest** → scan/validate stay deterministic;
  the LLM pass stays clearly delegated, consistent with `menu.py`'s `info_only`
  stance.

A minimal direct-API caller is still worth having **later**, as an *optional*
backend for headless mass batch — but as a plugin, not an MVP prerequisite.

**Impact on the plan:** Phase 3 becomes "dispatch to agent CLI"; the LLM Router
moves out of the critical path entirely. Sprint 1 no longer blocks on it.

---

## 2. Secondary hardening (in leverage order)

### 2.1 The parser is the real risk, not the API call
Phase 4 (LLM markdown → JSON) is where these rot. Make the prompt emit a strict
fenced JSON block against an explicit schema; validate the response against a JSON
Schema; on failure **re-prompt exactly once with the validation error injected**
(self-correction); then fall back to saving the raw response for manual review —
**never silently drop**. This is the project's "fail honestly" ethos applied to
the parser.

### 2.2 Stamp provenance from Phase 1, not Phase 6
The provenance loop was just closed (v2.2.0). `sopx compile` must stamp each
output with source hash + `upload_date` (already in `metadata.json`) + model +
timestamp (`run.json`), **and** propagate the `SOURCE_DATE` into the compiled
principles' provenance tags. Otherwise compile output isn't auditable by the
evolution audit — which reopens the exact gap v2.2.0 just fixed.

### 2.3 Grounding check is mandatory, not a Phase-5 nicety
`verify_concept_presence.py` **already exists**. Every extracted principle must
pass it: if its wording isn't grounded in the source transcript, **flag or drop
it**. The compiler is precisely where hallucination would enter, so the
anti-fabrication gate cannot be optional here — it's the project's whole reason
for existing.

### 2.4 Idempotent, resumable batch in Sprint 1 (not Sprint 3)
At 227-video scale, a batch that can't resume is unusable — a crash at video 140
must not restart from zero. Reuse the ingestion stage-cache discipline (`.done`
sentinel + atomic write), keyed by `(source hash + prompt version + model)`. And
a **dry-run that estimates whole-batch tokens/cost and requires confirmation
before spending** — that prevents the surprise bill more than the reactive
`cost_cap_per_batch` does.

### 2.5 Mandatory sampling review gate for batch mode (hard MVP requirement)

**Why this is not optional, not just "nice for quality":** §2.1/§2.3's automated
gates (schema validation, grounding check, coherence audit) only catch the
failure modes they were built to detect — an ungrounded claim, a cross-video
contradiction. They cannot catch a claim that **is** grounded (real words from
the transcript) but is **misread** — the wrong meaning attributed to real
source text. That failure mode has already happened in this exact codebase:
`run_report.json`/`validate_run_report.py` exists because an executor skipped
video-frame rescue citing "1.6GB," a misread of "1,600 snapshots/second" in
the transcript — plausible-sounding, passed every check that existed at the
time, and **nothing automated caught it**. Only a human reading the output
afterward did. Single-file `sopx compile` still has that human in the loop
implicitly (the operator sees the prompt and the output). **Batch mode removes
them** — a systematic misread that would be caught instantly in interactive
mode instead repeats identically across the whole batch before anyone looks.

**Mechanism:**
- Applies to `sopx compile <dir> --batch` only (single-file compile keeps its
  existing implicit human review).
- **Risk-weighted sampling, not uniform random.** Prioritize: the first item of
  every batch (calibration baseline), items with low coherence-audit
  confidence, items flagged `re_candidate` (Blackhat-candidacy — structurally
  more complex, higher misread risk), and the longest sources (most surface
  area for a subtle error). Default rate: `max(1, ceil(10% of batch))`,
  configurable via `--review-sample-rate`.
- **A real pause, not a log line.** At each sampled item, the batch halts and
  shows the compiled output (SOPs/principles/concepts) side-by-side with the
  cited source excerpt for each claim — the same review surface `--dry-run`
  already establishes for the single-file prompt. Operator: approve / reject /
  edit.
- **Reject fails loud by default.** A rejected sample aborts the remaining
  batch (mirrors the Chronology Gate's hard-fail precedent) rather than
  silently continuing past a caught error. `--continue-on-reject` is an
  explicit opt-in for the rare case where the operator wants to keep going and
  revisit flagged items later.
- **No silent bypass.** Running `--batch` with sampling disabled requires an
  explicit `--review-sample-rate 0`, not a missing flag defaulting to zero —
  the absence of review must be a decision the operator visibly made, not the
  default state.
- **The review itself becomes provenance.** Record in `run.json`: whether each
  item was sampled, by whom, when, and the approve/reject/edit decision. This
  extends the same "never silently authoritative" principle the v2.2.0
  provenance loop applied to dates — to the review step itself. Without this,
  a bad extraction that slips through later is indistinguishable from one that
  was never sampled at all; with it, an auditor can tell the difference.

---

## 3. What's good (keep as-is)
- Phase/CLI/risk-matrix structure and sprint ordering are clear and realistic.
- The epistemic-status + evidence-ref requirement is the right core — §2.3 just
  makes it mechanically enforced instead of prompt-hoped.
- `--dry-run` prompt preview is the right review surface to preserve as automation
  replaces the manual copy-paste.

---

## 4. One-line summary
The plan wants to "automate the hand-off by calling the API" — but the hand-off
already has a clean destination: the agent CLI the user already runs. Closing the
gap by subprocess to that agent collapses the blocking dependency, kills the
API-key footgun, and keeps the architecture true to itself. The real work isn't
the call — it's **robust parse + mandatory grounding + stamped provenance +** (per
§2.5) **a real human checkpoint at batch scale**, which is where the project's
anti-hallucination credibility is won or lost.

---

## 5. Addendum status

§2.5 was added after this review first landed, prompted by the maintainer
recalling the exact incident cited as precedent (they were the one who caught
it originally). It is a **hard MVP requirement**, not deferred hardening —
`sopx compile --batch` should not ship without it. If implementation of
`sopx compile` is already underway elsewhere when this addendum lands, review
its integration points against §2.5 specifically (sampling hook location,
`run.json` schema for the review record, and the `--review-sample-rate` /
`--continue-on-reject` CLI surface) rather than assuming it was designed in
from the start.
