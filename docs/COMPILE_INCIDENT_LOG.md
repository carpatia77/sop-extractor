
## Incident Log — sopx Compile Pipeline (2026-07-24)

### Incident CP1: Review gate ran post-loop instead of inline
- **Symptom**: `--review-sample-rate 1.0` with reject on first item — all 3 videos still compiled. "Abort remaining batch" only stopped reviewing, not compiling.
- **Root cause**: Review gate logic was placed AFTER the main compilation loop (line ~860). All agent calls and writes happened before any human review.
- **Fix**: Moved review check inside the per-item loop (after each write). Added `sample_indices` set computed before loop, checked inside loop. Reject now `break`s immediately.
- **Test**: `test_review_reject_stops_compilation` — 3-item batch, first rejected → asserts only 1 agent call, only 1 JSON written.
- **Commit**: `0d6b4a1`
- **Severity**: Architectural — defeated the entire purpose of §2.5

### Incident CP2: discover_sources picked up compilation/ output files
- **Symptom**: Second batch run found 47 sources instead of 26. Compiled `compilation/batch_summary.md` and `compilation/-sE1kz-fypI.txt.md` as if they were transcripts.
- **Root cause**: `rglob("*")` in `discover_sources()` traversed into `compilation/` subdirectory. The `.md` files written by previous runs had valid extensions and weren't excluded.
- **Fix**: Added `if "compilation" in f.parts: continue` to skip any file inside a `compilation/` directory.
- **Test**: `test_excludes_compilation_subdir`
- **Commit**: `2c61733`
- **Severity**: High — caused wasted API calls and incorrect output

### Incident CP3: claude CLI session limit hit during batch
- **Symptom**: `RuntimeError: Agent 'claude' failed (exit 1): You've hit your session limit · resets 10pm (America/Sao_Paulo)`
- **Root cause**: Batch compilation used `claude -p` subprocess which consumes the user's Claude Code session quota. 19 sequential calls exhausted the limit.
- **Fix**: None (operational). User completed remaining 7 compilations manually (operator-compiled).
- **Lesson**: Never run batch operations that consume external API quota without explicit operator authorization. Always confirm micro-decisions before executing.
- **Severity**: Critical (operational) — depleted user's session quota without permission

### Incident CP4: /tmp compilation output lost on session interrupt
- **Symptom**: 19 compiled JSON files in `/tmp/compile_txt/compilation/` disappeared after session was interrupted by rate limit.
- **Root cause**: Output was written to `/tmp` (ephemeral) instead of the persistent output directory. Session interruption cleaned up temp files.
- **Fix**: Operator re-compiled the 7 remaining videos directly into `output/quantguild_transcripts/compilation/`.
- **Lesson**: Never write production output to `/tmp`. Use the project's output directory structure.
- **Severity**: Medium — data loss, required re-compilation

### Incident CP5: Circular import between compile.py and review_gate.py
- **Symptom**: `ImportError: cannot import name 'compute_sample_indices' from partially initialized module 'scripts.review_gate'`
- **Root cause**: `review_gate.py` imported `grounding_check` from `compile.py`, which imported from `review_gate.py` — circular dependency.
- **Fix**: Removed unused `grounding_check` import from `review_gate.py`. Dependency is one-way: compile.py → review_gate.py.
- **Severity**: Medium — prevented all tests from running until fixed

---

### Rules derived from incidents

1. **Never consume external API quota without explicit operator authorization** — CP3
2. **Write production output to project directories, never /tmp** — CP4
3. **Review gates must be inside work loops, not after** — CP1
4. **Exclude output directories from recursive source discovery** — CP2
5. **Avoid circular imports between pipeline modules** — CP5
6. **After 3+ failures, full rewrite not patches** — inherited from C6/C8
