
## Incident Log — Web Console + Pipeline E2E (2026-07-29)

### Incident WC1: --compile flag in web_server passed to run.py (non-existent)
- **Symptom**: All 3 PDF uploads returned "unrecognized arguments: --compile" — pipeline failed silently.
- **Root cause**: `web_server.py` called `run.py` with `--compile` flag, but `run.py` already handles ingest+compile internally and doesn't accept that flag.
- **Fix**: Removed `--compile` from the command in `web_server.py` (1-line change).
- **Test**: Manual — 3 PDFs processed successfully after fix.
- **Commit**: `db3ad13`
- **Severity**: High — total pipeline failure on all uploads

### Incident WC2: compile.py reads PDFs as UTF-8 text
- **Symptom**: `'utf-8' codec can't decode byte 0xd0 in position 10` — PDF compilation failed with 0 output.
- **Root cause**: `compile.py:764` used `filepath.read_text(encoding="utf-8")` for all files, including binary PDFs.
- **Fix**: Added `_extract_pdf()` function using `pdfplumber` to extract text from PDF pages before compilation.
- **Test**: 9-page PDF extracted 14,233 chars successfully.
- **Commit**: `9f8ddd8`
- **Severity**: High — PDFs completely unusable through web console

### Incident WC3: WSL browser auto-open fails
- **Symptom**: `sopx web` started server but didn't open browser (WSL environment).
- **Root cause**: `webbrowser.open()` doesn't work in WSL — no browser in Linux environment.
- **Workaround**: Added `--no-browser` flag; user opens `http://localhost:8080` manually.
- **Severity**: Low — UX friction, not a bug

### Incident WC4: require_evidence gate fails on all real SF output
- **Symptom**: `--require-evidence` rejects every concept and reference node (the majority of SF nodes).
- **Root cause**: `build_semantic_field()` sets `evidence_id=None` for concepts and references by construction. Only principles and SOPs receive evidence_id.
- **Fix**: Scoped gate to `_EVIDENCE_REQUIRED_TYPES = {"principle", "sop"}` — concepts/references excluded.
- **Test**: Real SF now passes `require_evidence=True` with zero errors.
- **Commit**: `5ae8052`
- **Severity**: Medium — gate was advertised as feature but unusable in practice

### Incident WC5: contradicts self-loop models non-existent relation
- **Symptom**: `contradicts` edge generated as self-loop (source == target), representing "principle contradicts itself".
- **Root cause**: `dissent_type: contradicts` means an external counter-argument challenges the principle, not that it self-contradicts. No external counter-argument node exists in the graph.
- **Fix**: Removed `contradicts` from `VALID_EDGE_TYPES` entirely — same criterion as `derives_from` (no generator between distinct nodes). Refutation data stays on principle nodes.
- **Test**: Enum now `{used_in, supports, requires, references}` — 4 types, all with real generators.
- **Commit**: `ff13b26`
- **Severity**: Medium — false promise (edge type declared but semantically wrong)

### Incident WC6: Contradicts/derives_from asymmetry in enum treatment
- **Symptom**: `derives_from` removed for having no generator; `contradicts` kept with artificial self-loop generator.
- **Root cause**: Inconsistent application of "remove types with no real generator" criterion.
- **Fix**: Both removed from enum. Same standard applied symmetrically.
- **Lesson**: When removing a type for "no generator", check all types against the same bar in the same commit.
- **Severity**: Low — modelled incorrectly but didn't crash

---

## Summary

| # | Incident | Severity | Fix Commit | Status |
|---|----------|----------|------------|--------|
| WC1 | --compile flag non-existent | High | `db3ad13` | ✅ Fixed |
| WC2 | PDF read as UTF-8 | High | `9f8ddd8` | ✅ Fixed |
| WC3 | WSL browser auto-open | Low | N/A (workaround) | ✅ Mitigated |
| WC4 | require_evidence unusable | Medium | `5ae8052` | ✅ Fixed |
| WC5 | contradicts self-loop wrong | Medium | `ff13b26` | ✅ Fixed |
| WC6 | Contradicts/derives_from asymmetry | Low | `ff13b26` | ✅ Fixed |

### Patterns Observed
1. **"Declared ≠ Delivered"**: Features announced in CHANGELOG/commit message before verifying they work on real data. The `require_evidence` gate and `contradicts` edge type were both functionally broken on real output despite passing synthetic tests.
2. **Synthetic tests ≠ production**: Tests used hand-crafted SFs with all fields populated; real `build_semantic_field()` output has `evidence_id=None` on 2/4 node types.
3. **Cross-module flag mismatch**: `web_server.py` passed `--compile` to `run.py` — two modules in the same project with incompatible interfaces.
