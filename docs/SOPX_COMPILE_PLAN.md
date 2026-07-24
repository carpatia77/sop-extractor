# Plan: `sopx compile` — Automated Knowledge Compilation Pipeline

**Status**: Draft for engineer review
**Date**: 2026-07-24
**Author**: MiMo Code + operator
**Context**: Validated manually with 26 QuantGuild transcripts (72,845 words, 3 parallel agents, 1,294 lines of compiled output)

---

## 1. Problem Statement

The pipeline has two working endpoints:
- **`sopx scan --emit-prompt`** → generates extraction prompts (automated)
- **Agent + SKILL.md** → compiles knowledge into SOPs/principles/concepts (manual hand-off)

The **gap**: the hand-off between prompt generation and agent execution is manual (copy-paste). This blocks scalability — compiling 227 videos requires 227 manual copy-paste operations.

## 2. Hand-Off Architecture (Current vs Proposed)

### Current (Manual)
```
sopx scan file.txt --emit-prompt
    → prints prompt to stdout
    → operator copies prompt
    → operator pastes into Claude/Copilot/Amp
    → agent follows SKILL.md Steps 0-9
    → agent produces output
    → operator saves output
```

### Proposed (Automated)
```
sopx compile <input> [--output <dir>] [--model <model>] [--batch]
    → scan (auto-detect type)
    → generate prompt (structured)
    → call LLM API (via llm_router)
    → parse response (extract SOPs/principles/concepts)
    → validate (coherence audit, epistemic status)
    → write output (compilation/*.md + compilation/*.json)
    → stamp provenance (run.json)
```

## 3. Detailed Phase Design

### Phase 1: Scan & Classify

**Input**: File path (transcript .txt, .srt, book .pdf, etc.)

**Implementation**:
- Reuse `preflight_scan.scan_source()` — already handles all source types
- Detect: file type, word count, language, RE candidate status
- For batch mode: iterate over directory, scan each file

**Output**:
```python
{
    "path": "transcripts/LX4Ugaxx9n0.txt",
    "source_kind": "transcript",
    "recommendation": "text",
    "confidence": "medium",
    "word_count": 9012,
    "re_candidate": True,
    "analyst_lens_suggestion": {"lens": "systems-architect"}
}
```

### Phase 2: Prompt Generation

**Input**: Scan result + compilation instructions

**Implementation**:
- Extend `build_prompt_draft()` to support a `compile` mode
- The prompt must specify:
  1. **Output format**: JSON with SOPs, principles, concepts, references
  2. **Epistemic status**: mandatory (certain/probable/speculative)
  3. **Evidence linkage**: every claim must reference source line/segment
  4. **Conciseness**: decision logic only, no summaries
  5. **Cross-reference instructions**: for batch mode, instructions to note contradictions and overlapping concepts

**Prompt template** (compile mode):
```
You are a knowledge compiler. Read the following source and extract:

1. SOPs: Step-by-step procedures the author teaches. Format:
   - Name of procedure
   - Steps (numbered)
   - When to use (decision conditions)

2. Fundamental Principles: Absolute rules the author states. Format:
   - Statement (one sentence)
   - Epistemic status: certain | probable | speculative
   - Evidence: line/segment reference

3. Key Concepts: Technical terms with definitions. Format:
   - Term
   - Definition (one sentence)
   - Where used (which SOPs/principles reference it)

4. Named References: People, papers, books, models mentioned.

RULES:
- Extract DECISION LOGIC, not summaries
- Every claim must have epistemic status
- Every claim must reference source text
- Do not fabricate — if uncertain, mark as speculative
- Be concise — one line per principle

Source: {path}
Content: {content}
```

### Phase 3: LLM Call (The Hand-Off)

**Input**: Compiled prompt + routing config

**Implementation**:
- New module: `sopx/compile/llm_caller.py`
- Uses the planned LLM Router (routing table: task_type × complexity × budget → model)
- For compilation: `task_type="extraction"`, complexity based on word count
- BYOK model: user provides API key via `~/.config/sopx/config.yaml`
- Retry logic: exponential backoff on API errors
- Token budget: ~4K tokens per 1K words of source
- For sources >50K words: split into chunks, compile each, then cross-reference

**Supported backends** (initial):
- OpenAI (GPT-4o-mini for cheap, GPT-4o for standard)
- Anthropic (Haiku for cheap, Sonnet for standard)
- Local (Ollama, llama.cpp) — future

**Cost estimation** (from MEMORY.md):
- Economico: ~$0.04/video (GPT-4o-mini)
- Equilibrado: ~$0.22/video (Sonnet)
- Premium: ~$1.02/video (Opus)

### Phase 4: Parse & Structure

**Input**: Raw LLM response (markdown/JSON)

**Implementation**:
- New module: `sopx/compile/parser.py`
- Parse structured output from LLM:
  - Extract SOPs (numbered steps)
  - Extract principles (one-liners with epistemic status)
  - Extract concepts (term + definition)
  - Extract references (names, papers, models)
- Validate structure: every SOP has steps, every principle has epistemic status
- If parse fails: retry once with stricter prompt, then flag for manual review

**Output format** (per video):
```json
{
    "video_id": "LX4Ugaxx9n0",
    "title": "The Ultimate Guide to Quant Portfolio Management",
    "sops": [
        {
            "name": "Portfolio Construction Decision Flow",
            "steps": ["Define goals...", "Identify assets...", ...],
            "decision_conditions": "When building a new portfolio"
        }
    ],
    "principles": [
        {
            "statement": "Higher returns require higher risk",
            "epistemic_status": "certain",
            "evidence_ref": "line 45-52"
        }
    ],
    "concepts": [
        {
            "term": "Volatility Drag",
            "definition": "The penalty geometric compounding imposes on volatile portfolios",
            "used_in": ["Portfolio Construction Decision Flow", "Sharpe Optimization"]
        }
    ],
    "references": ["Black-Scholes", "CAPM", "Jane Street", "Citadel"]
}
```

### Phase 5: Validate

**Input**: Structured compilation output

**Implementation**:
- Reuse existing validators:
  - `validate_coherence_audit.py` — checks for contradictions within source
  - `verify_concept_presence.py` — checks that extracted concepts are grounded in source
- New validation rules:
  - Every principle must have epistemic_status (not empty)
  - Every SOP must have ≥2 steps
  - Every concept must have a definition
  - Cross-video: flag contradictions between videos (same channel, different claims)

### Phase 6: Output

**Input**: Validated compilation

**Implementation**:
- Directory structure:
```
output/<channel>/
├── transcripts/          # raw SRT/TXT (from ingestion)
├── compilation/
│   ├── LX4Ugaxx9n0.json     # per-video structured output
│   ├── LX4Ugaxx9n0.md       # per-video human-readable
│   ├── SOPs.md               # all SOPs consolidated
│   ├── principles.md         # all principles consolidated
│   ├── concepts.json         # concept graph
│   ├── cross_analysis.md     # topic clusters, correlations
│   └── run.json              # provenance (model, timestamp, hashes)
├── metadata/             # from ingestion (upload_date, word_count)
└── set_manifest.json     # cross-video manifest
```

## 4. CLI Interface

```bash
# Single file compilation
sopx compile output/quantguild_transcripts/LX4Ugaxx9n0.txt

# Batch compilation (entire directory)
sopx compile output/quantguild_transcripts/ --batch

# With model override
sopx compile output/quantguild_transcripts/ --model gpt-4o-mini

# With budget tier
sopx compile output/quantguild_transcripts/ --budget economico

# Dry-run (show prompt without calling LLM)
sopx compile output/quantguild_transcripts/LX4Ugaxx9n0.txt --dry-run

# Cross-analysis only (after batch compile)
sopx compile output/quantguild/ --cross-analysis
```

## 5. Implementation Order

### Sprint 1: Core compile (1 week)
1. `sopx/compile/__init__.py` — module scaffold
2. `sopx/compile/llm_caller.py` — API integration (OpenAI first)
3. `sopx/compile/parser.py` — parse LLM output to structured JSON
4. `sopx compile <file>` — single file, no batch
5. `sopx compile <file> --dry-run` — prompt preview

### Sprint 2: Batch + validation (1 week)
1. `sopx compile <dir> --batch` — process entire directory
2. Integrate coherence audit for per-video validation
3. `sopx compile <dir> --cross-analysis` — generate cross-analysis
4. Provenance stamping (run.json)

### Sprint 3: Optimization (1 week)
1. Chunking for large sources (>50K words)
2. Cost tracking per compilation
3. Cache: skip recompilation if source unchanged
4. Model routing (cheap vs standard based on complexity)

## 6. Dependencies

| Dependency | Status | Required For |
|---|---|---|
| LLM Router | **Not implemented** | Phase 3 (API calls) |
| `preflight_scan.py` | **Implemented** | Phase 1 (scan) |
| `validate_coherence_audit.py` | **Implemented** | Phase 5 (validation) |
| `verify_concept_presence.py` | **Implemented** | Phase 5 (grounding check) |
| `build_set_manifest.py` | **Implemented** | Phase 6 (cross-video manifest) |
| Config Manager (`sopx/config.py`) | **Implemented** | API key storage |
| Cache Manager (`sopx/cache.py`) | **Implemented** | Skip recompilation |

**Critical path**: LLM Router is the blocking dependency. Without it, Phase 3 cannot make API calls. Options:
1. Implement full LLM Router (routing table, BYOK, cost tracking)
2. Minimal: direct OpenAI/Anthropic client calls (no routing, no cost tracking)
3. Interim: use subprocess to call `claude` or `copilot` CLI (wraps existing agents)

## 7. Risk Matrix

| Risk | Severity | Mitigation |
|---|---|---|
| LLM API rate limits during batch | High | Rate limiting (2s between calls), exponential backoff |
| LLM output format inconsistency | High | Parser with retry + fallback to manual review prompt |
| Cost runaway on large batches | Medium | Budget caps per batch, cost estimation before run |
| Hallucinated SOPs/principles | High | Coherence audit + concept grounding check |
| Source > context window | Medium | Auto-chunk at 40K tokens, cross-reference chunks |
| API key exposure | Critical | Never in logs, env vars only, config.yaml with 0600 perms |

## 8. Success Metrics

| Metric | Target |
|---|---|
| Compilation accuracy (SOPs found vs human) | >80% |
| Principle extraction precision | >90% (low false positives) |
| Cost per video (economico tier) | <$0.05 |
| Time per video (batch mode) | <30s |
| Batch throughput (227 videos) | <2h total |

## 9. Validation Against QuantGuild Test

The manual test with 26 videos produced:
- **392 lines** of portfolio/volatility compilation
- **335 lines** of risk/strategy compilation
- **414 lines** of career/mindset compilation
- **153 lines** of cross-analysis

These documents serve as the **golden set** for validating `sopx compile`:
1. Run `sopx compile` on the same 26 transcripts
2. Compare output against manual compilation
3. Measure: SOP recall, principle precision, concept coverage
4. Iterate until >80% overlap with manual output

---

## Appendix A: File Inventory (New)

```
sopx/compile/
├── __init__.py         # Module init
├── llm_caller.py       # LLM API integration
├── parser.py           # Parse LLM output to structured JSON
├── prompt_gen.py       # Generate compilation prompts
├── chunker.py          # Split large sources for context window
├── validator.py        # Post-compilation validation
└── output.py           # Write structured output files

tests/test_compile.py   # Unit tests
tests/test_compile_e2e.py  # End-to-end with mock LLM
```

## Appendix B: Config Additions

```yaml
# ~/.config/sopx/config.yaml additions
compile:
  default_model: gpt-4o-mini        # or anthropic/claude-3-haiku
  budget_tier: economico            # economico | equilibrado | premium
  max_tokens_per_chunk: 40000
  retry_attempts: 3
  rate_limit_delay: 2.0             # seconds between API calls
  cost_cap_per_batch: 5.00          # USD, abort if exceeded
```
