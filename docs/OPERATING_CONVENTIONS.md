# Operating Conventions (Human-in-the-Loop)

This project relies on a human operator working in tandem with the validation suite (`validate_all.py`). Because there is no automated programmatic daemon or extraction loop in the background, robust quality control depends on explicit operating discipline.

Do not attempt to build "circuit breakers", automated loops, or retry policies in code. Instead, adhere strictly to the conventions below.

## 1. Re-run Cap (The "Three Strikes" Rule)
If an isolated audit (Coherence or Temporal Evolution) fails its respective validator **3 times in a row**, stop instructing the agent to regenerate it. 
A persistent failure is a strong signal that either the underlying source material lacks the necessary logic, or the prompt/instructions are mismatched to the domain.
- **Action:** Stop re-running. Investigate the source, the generated `.md` files, or the prompt. A failure is a signal, not a retry candidate.

## 2. Final Human QA Gate
Before any set or skill is considered "published" (ready for consumption or merging), a human operator MUST:
1. Confirm that `python scripts/validate_all.py <dir>` exits cleanly (green output).
2. **Eyeball `<set>_current.md` (and the `sops.md` / `first_principles.md` files) for completeness.**
- **Why:** The automated validation gates catch *fabrication* (via strict text matching) and *contradiction* (via coherence audits). However, no automated gate can reliably catch **omission** (the LLM silently skipping a crucial concept). Only a human familiar with the source domain can verify if a load-bearing concept was omitted.

## 3. Model & Prompt Record (Traceability)
Never publish a set without stamping its provenance and run state.
- Before considering the work done, you MUST run `python scripts/validate_all.py <dir> --write-run --model <model-used> --audit-model <audit-model-used>`.
- This ensures a `run.json` is saved within the set directory, documenting the exact models and prompt version used, along with the hashes of the artifacts. This allows `detect_changes.py` to function later and guards against model drift.

## 4. Cross-Model Audits
Whenever possible, run the extraction phase on one model family (e.g., Claude 3.5 Sonnet) and run the isolated Coherence/Temporal audits on a **different** model family (e.g., GPT-4o).
- **Why:** A different model is much less likely to rubber-stamp the first model's phrasing or overlook its blind spots. This provides the 80% benefit of multi-agent voting without the heavy infrastructure.

## 5. Extraction Pre-Flight Review
Before handing a pre-answered "Full Conversion" prompt (`BOOK_TYPE`, `DEPTH`, name/destination, lineage) to an executor, run `python scripts/preflight_scan.py <source>` and fill in `docs/EXTRACTION_PREFLIGHT_CHECKLIST.md`.
- **Why:** these Steps (1.5, 4, 5, 5.5 in `SKILL.md`) are written as a live Q&A but get pre-answered for unattended runs; nothing in the pipeline validates the pre-answers before extraction starts. A wrong `BOOK_TYPE` in particular (e.g. calling a table/diagram-driven source "text-heavy" when its core argument is carried by tables or diagrams) is expensive to discover after a full run has already completed — this can happen with any source in any field, not just an obvious edge case.
