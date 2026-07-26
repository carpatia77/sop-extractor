# Release v3.0.0 — Anti-Hallucination Pipeline + Teaching System + Wizard

**Date**: 2026-07-26
**Commits**: 26 commits since v2.2.0
**Tests**: 960 collected (955 passed + 2 skipped + 3 ambient)

---

## Highlights

### Anti-Hallucination Pipeline
Every claim is now stress-tested before publication. The Refutation Chain generates counter-arguments for each principle, the Evidence Ledger tracks provenance with SRT timestamps, and Emerging Questions detect gaps in the knowledge graph.

### Teaching System (Método Hebraico)
6-session interactive study system with stateful progress. Each session creates its own output, gates enforce ordering and file existence, and the Chavruta Engine provides Socratic-style debate with 7 depth levels.

### Knowledge Export
HTML Viewer (self-contained, force-directed graph) and LightRAG/Cognee adapter (compatible JSON format) — the pipeline now serves both human and machine consumption.

### Wizard
Interactive guided workflow that reduces CLI friction from 14 commands to 4 guided flows. subprocess.run (no shell injection), non-interactive handling, returncode checking.

---

## What's New

### Anti-Hallucination Pipeline
- `scripts/refutation_chain.py` — Per-claim stress-testing
- `scripts/evidence_ledger.py` — Deterministic provenance
- `scripts/emerging_questions.py` — Gap/tension/limit detection
- Refutation fields in principle nodes (strongest_alternative, disconfirming_evidence, dissent_type)
- Evidence Ledger with locator (SRT timestamps), excerpt_hash, entry_id

### Teaching System
- `scripts/chavruta/` — sf_matcher, drift_detector, depth_tracker, engine
- `scripts/teach/` — session_manager + 6 session modules
- Depth scoring grounded in graph events (1-7, chess analogy)
- Drift detection with 2 active anchors + contradiction override
- 6-session stateful flow with enforced gates

### Knowledge Export
- HTML Viewer (self-contained, interactive, no deps)
- LightRAG/Cognee adapter (compatible JSON format)

### CLI
- `sopx teach` — start/status/complete subcommands
- `sopx wizard` — interactive guided workflow

### Security
- Command injection fixed (os.system → subprocess.run)
- Non-interactive handling (no infinite loops)
- Returncode checking (no silent failures)

---

## Breaking Changes
- **Renamed "Método Judaico" → "Método Hebraico"** across code and docs
- **Version bump**: 2.2.0 → 3.0.0 (major: teaching system addition)

---

## Stats
- **960 tests** (955 passed + 2 skipped + 3 ambient)
- **ruff clean** (CI command verified)
- **~20,000 lines** of new/modified code
- **13 new modules** (scripts/ + scripts/chavruta/ + scripts/teach/)
- **Pareto ~100%** (11/13 components complete, LLM Router + VLM optional)

---

## Upgrade

```bash
pip install --upgrade sop-extractor==3.0.0
```

Or from source:
```bash
git pull
pip install -e .
```
