# Refutation Chain — Evidence Ledger Completion

## Goal
Implement the Refutation Chain (Layer 4, component D3) to complete the Evidence Ledger at 100%. For every extracted principle/claim, generate a strongest counter-argument and disconfirming evidence, then validate the alternative genuinely opposes the original claim.

## Architecture References
- `docs/xhal2049-layers.md:43` — Refutation Builder (strongest_alternative + disconfirming)
- `docs/xhal2049-risk-matrix.md:145` — 4.3: claim → LLM → strongest_alternative
- `docs/xhal2049-risk-matrix.md:155` — Risk: refutation confirms instead of contradicting
- `docs/xhal2049-risk-matrix.md:166-167` — test_refutation_direction, test_refutation_confirmation_bias

---

## 1. Data Model

### Refutation Entry (added to each principle in compilation JSON)

```json
{
  "statement": "Volatility drag compounds against you over time",
  "epistemic_status": "certain",
  "evidence": "...",
  "refutation": {
    "strongest_alternative": "Volatility drag is mathematically real but its impact depends on path — geometric mean underperforms arithmetic mean, but rebalancing can capture volatility harvesting premium",
    "disconfirming_evidence": "Would be false if Sharpe ratio were path-independent, or if log-returns were additive",
    "dissent_type": "qualifies",  // qualifies | contradicts | context_limited
    "confidence": 0.85,           // how strong is the counter-argument (0-1)
    "generated_at": "2026-07-25T10:00:00Z",
    "model": "claude"
  }
}
```

**dissent_type** classification:
- `contradicts` — directly opposes the claim
- `qualifies` — narrows scope or adds conditions (most common)
- `context_limited` — claim is true in context X but not Y

---

## 2. New Script: `scripts/refutation_chain.py`

### Structure (~300 lines)

```
scripts/refutation_chain.py
├── REFUTATION_PROMPT (template for LLM call)
├── build_refutation_prompt(claim, evidence, source_content) → str
├── call_refutation_agent(prompt, agent, model, timeout) → dict
├── parse_refutation_response(text) → dict
├── validate_refutation(claim, refutation) → tuple[bool, str]
│   ├── _semantic_overlap(claim, alternative) → float  # Jaccard on salient terms
│   └── _is_genuine_dissent(claim, alternative, threshold=0.3) → bool
├── enrich_principles(principles, source_content, ...) → tuple[list, list]
├── run_refutation_chain(compilation, source_content, ...) → dict
└── main()  # argparse CLI
```

### Key Functions

#### `build_refutation_prompt(claim, evidence, source_content) → str`
```python
REFUTATION_PROMPT = """\
You are a critical reviewer. For the following claim extracted from source material,
generate the STRONGEST counter-argument or alternative interpretation.

CLAIM: {claim}
EVIDENCE FROM SOURCE: {evidence}

Respond in this EXACT format:
- **Strongest Alternative**: <best counter-argument or qualifying condition>
- **Disconfirming Evidence**: <what would need to be true for the original claim to be wrong>
- **Dissent Type**: qualifies | contradicts | context_limited

RULES:
1. The alternative MUST genuinely oppose or narrow the original claim
2. Do NOT simply rephrase or agree with the claim
3. Be specific — name the exact condition under which the claim fails
4. Keep it concise — one sentence each for alternative and disconfirming evidence

SOURCE EXCERPT (for context):
{source_excerpt}
"""
```

#### `validate_refutation(claim, refutation) → tuple[bool, str]`
Deterministic validation — no LLM call:
1. **Semantic overlap check**: Extract salient terms from claim and alternative using `verify_concept_presence.salient_terms()`. Compute Jaccard similarity. If > 0.7, the alternative is too similar (likely confirming, not contradicting).
2. **Negation check**: Check for negation words in alternative that don't appear in claim (e.g., "not", "unless", "except", "only when", "depends on").
3. **Scope narrowing check**: Check for qualifying language ("in most cases", "generally", "depends on") that indicates the alternative narrows rather than confirms.

Returns `(is_valid, reason)` where reason explains why validation failed if applicable.

#### `enrich_principles(principles, source_content, agent, model, ...) → tuple[list, list]`
For each principle:
1. Build refutation prompt
2. Call agent via subprocess (reuse `compile.call_agent` pattern)
3. Parse response
4. Validate refutation
5. Attach `refutation` dict to principle
6. If validation fails, log warning but still attach (human review decides)

Returns `(enriched_principles, flagged_principles)`

#### `run_refutation_chain(compilation, source_content, ...) → dict`
Main entry point. Takes compilation JSON, adds refutation to each principle. Returns enriched compilation.

### CLI Interface

```bash
# Enrich a single compilation JSON
python scripts/refutation_chain.py output/compilation/video.json

# Enrich all compilations in batch
python scripts/refutation_chain.py output/compilation/ --batch

# Dry run (show prompts only)
python scripts/refutation_chain.py output/compilation/video.json --dry-run

# Override agent/model
python scripts/refutation_chain.py output/compilation/video.json --model sonnet

# Validation threshold
python scripts/refutation_chain.py output/compilation/video.json --overlap-threshold 0.7
```

---

## 3. Integration into compile.py

### Insertion Point: After grounding check (line 841), before write_compilation (line 844)

```python
# Refutation chain (§2.7) — adversarial quality gate
if args.refutation_chain and all_sections["principles"]:
    from refutation_chain import enrich_principles
    synonym_map = load_domain_synonyms(args.domain) if args.domain else None
    enriched, refutation_flagged = enrich_principles(
        all_sections["principles"], content,
        agent=args.agent, model=args.model, timeout=args.timeout,
        overlap_threshold=args.refutation_overlap_threshold,
    )
    if refutation_flagged:
        print(f"  Refutation: {len(refutation_flagged)} principles flagged "
              f"(overlap or validation issue)")
    all_sections["principles"] = enriched
```

### New CLI Arguments in compile.py

```python
parser.add_argument("--refutation-chain", action="store_true", default=True,
                    help="Generate refutation chains for principles (default: on)")
parser.add_argument("--no-refutation-chain", action="store_false", dest="refutation_chain",
                    help="Disable refutation chain generation")
parser.add_argument("--refutation-overlap-threshold", type=float, default=0.7,
                    help="Max semantic overlap between claim and alternative (default 0.7)")
```

### Output JSON Addition

The compilation JSON gains a `refutation_summary` field:

```json
{
  "source": "video.txt",
  "principles": [...],
  "refutation_summary": {
    "total": 5,
    "enriched": 5,
    "flagged": 1,
    "dissent_types": {"qualifies": 3, "contradicts": 1, "context_limited": 1}
  }
}
```

---

## 4. Validation Logic (Deterministic)

### `_semantic_overlap(claim, alternative) → float`
```python
def _semantic_overlap(claim: str, alternative: str) -> float:
    """Jaccard similarity of salient terms between claim and alternative."""
    from verify_concept_presence import salient_terms
    t_claim = set(salient_terms(claim))
    t_alt = set(salient_terms(alternative))
    if not t_claim or not t_alt:
        return 0.0
    return len(t_claim & t_alt) / len(t_claim | t_alt)
```

### `_is_genuine_dissent(claim, alternative, threshold=0.7) → tuple[bool, str]`
```python
def _is_genuine_dissent(claim: str, alternative: str, threshold: float = 0.7) -> tuple[bool, str]:
    """Check if alternative genuinely opposes the claim."""
    overlap = _semantic_overlap(claim, alternative)
    if overlap > threshold:
        return False, f"Semantic overlap {overlap:.2f} > {threshold} — alternative may be confirming"
    
    # Check for negation/qualification in alternative
    negation_words = {"not", "never", "unless", "except", "only", "depends", "generally", "usually"}
    alt_lower = alternative.lower()
    has_negation = any(w in alt_lower for w in negation_words)
    
    if overlap < 0.1 and not has_negation:
        return False, f"Semantic overlap {overlap:.2f} too low and no negation — possible unrelated text"
    
    return True, "OK"
```

---

## 5. Test Plan: `tests/test_refutation_chain.py`

### Test Cases (from risk matrix + design)

```python
class TestRefutationChain:
    # --- Data model ---
    def test_refutation_entry_has_required_fields():
        """refutation dict must have strongest_alternative, disconfirming_evidence, dissent_type"""
    
    def test_dissent_type_enum():
        """dissent_type must be one of: qualifies, contradicts, context_limited"""
    
    # --- Validation: direction ---
    def test_refutation_direction():
        """Alternative must genuinely differ from claim"""
    
    def test_refutation_confirmation_bias():
        """Alternative that merely confirms the claim must be flagged"""
    
    def test_refutation_same_words_different_meaning():
        """Alternative with high word overlap but negation must pass"""
    
    # --- Validation: edge cases ---
    def test_empty_claim():
        """Empty claim should skip refutation, not crash"""
    
    def test_very_short_claim():
        """Single-word claim should produce meaningful alternative"""
    
    def test_high_overlap_flagged():
        """Overlap > 0.7 should flag the refutation"""
    
    def test_low_overlap_with_negation_passes():
        """Low overlap + negation words should pass validation"""
    
    def test_low_overlap_without_negation_flagged():
        """Low overlap without negation should flag (possibly unrelated)"""
    
    # --- Integration ---
    def test_enrich_principles_adds_refutation():
        """enrich_principles should add refutation dict to each principle"""
    
    def test_enrich_principles_dry_run():
        """dry_run should return prompts without calling agent"""
    
    def test_refutation_summary_in_output():
        """Compilation JSON should include refutation_summary"""
    
    # --- Failure modes ---
    def test_agent_timeout():
        """Agent timeout should log warning, skip principle, not crash batch"""
    
    def test_agent_empty_response():
        """Empty agent response should log warning, skip principle"""
    
    def test_malformed_response():
        """Malformed response should be caught by parser, skip principle"""
    
    # --- Compile integration ---
    def test_compile_with_refutation_chain():
        """compile.py --refutation-chain should add refutation to principles"""
    
    def test_compile_without_refutation_chain():
        """compile.py --no-refutation-chain should skip refutation"""
```

---

## 6. Edge Cases and Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Agent timeout per-principle | Principle lacks refutation | Log warning, skip, continue batch |
| Agent returns confirming text | False quality gate | Validation catches overlap > threshold |
| Agent returns unrelated text | Noise in output | Validation catches overlap < 0.1 |
| Malformed response format | Parse failure | try/except in parser, skip principle |
| Very long claim exceeds prompt | Truncation | Chunk or truncate claim to 500 chars |
| 26 principles × 1 agent call each | ~15-25 min added to batch | Sequential with 2s delay (existing pattern) |

---

## 7. Files to Create/Modify

| File | Action | Lines (est.) |
|------|--------|-------------|
| `scripts/refutation_chain.py` | **CREATE** | ~300 |
| `tests/test_refutation_chain.py` | **CREATE** | ~250 |
| `scripts/compile.py` | **EDIT** (add --refutation-chain flag + integration) | ~30 |
| `scripts/semantic_field.py` | **EDIT** (add refutation fields to principle nodes) | ~15 |

---

## 8. Verification

1. **Unit tests**: `pytest tests/test_refutation_chain.py -v` — all tests pass
2. **Integration test**: `python scripts/compile.py tests/test_source.txt --refutation-chain --dry-run` — shows refutation prompts
3. **Existing tests**: `pytest tests/ -v` — all 163+ tests still pass
4. **Ruff**: `ruff check scripts/refutation_chain.py` — clean
5. **Manual test**: Compile a real transcript with `--refutation-chain`, inspect output JSON for refutation fields
6. **Validation test**: Manually craft a confirming alternative, verify it gets flagged

---

## 9. Implementation Order

0. **Git**: Copy plan to `docs/REFUTATION_CHAIN_PLAN.md`, commit, and push to remote for audit review
1. Create `scripts/refutation_chain.py` with data model + validation functions
2. Create `tests/test_refutation_chain.py` with all test cases
3. Run tests — ensure validation logic works
4. Add LLM prompt + agent call + parser
5. Add `enrich_principles()` and `run_refutation_chain()`
6. Add CLI interface
7. Integrate into `compile.py` (flag + post-grounding step)
8. Update `semantic_field.py` to include refutation fields in principle nodes
9. Run full test suite + ruff
10. Manual test with real transcript
