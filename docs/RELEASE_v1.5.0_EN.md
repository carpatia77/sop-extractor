# Release v1.5.0 — Provenance Loop Closure

**Date:** 2026-07-24
**Type:** Feature release (minor)

---

## Summary

This release closes the **provenance loop** between ingestion and temporal audit — the core functionality that differentiates sop-extractor from any other knowledge tool on the market.

---

## What Changed

### New: `sopx set-build` — Automatic Manifest Builder

The `set-build` command auto-populates `set_manifest.json` from ingestion metadata, closing the gap between "what was ingested" and "what the Chronology Gate audits".

```bash
# Build manifest from ingested outputs
sopx set-build ./my-set --source output/vid1 --source output/vid2

# Auto-detect all outputs
sopx set-build ./my-set --from-outputs output/

# Preview without writing
sopx set-build ./my-set --dry-run
```

**Features:**
- Automatic extraction of `upload_date` and `canonical_id` from `metadata.json`
- Conversion of `canonical_id` to valid `source_id` (slugify)
- Chronological sequence inference
- Idempotent merge (preserves human corrections)
- Validation with real `validate_manifest.py` (fail-fast)

### New: `SOURCE_DATE` in Extraction Prompt

The extraction prompt now includes the measured date from ingestion:

```
Configuration (auto-detected + defaults — review):
  BOOK_TYPE = transcript  ([measured] Transcript (.srt/.vtt))
  DEPTH     = study  [default: study]
  Name      = mydssrs-b5u
  SOURCE_DATE = 2026-07-22  [measured from ingestion]  ← NEW
```

**Honesty rule:**
- Date exists → `SOURCE_DATE = YYYY-MM-DD [measured from ingestion]`
- Date missing → `SOURCE_DATE = <fill in> [not detected]`
- **Never fabricates data**

---

## Honesty Design (Core Philosophy)

The provenance loop follows the **"propose, don't guess"** philosophy:

1. **Measured dates enter as proposals** (`date_source: "ingested"`), never silently authoritative
2. **No date → empty field + `needs_date` flag**, never fabricated
3. **Re-run preserves human corrections** (`date_source: "manual"`)
4. **Fail-fast**: manifest with empty date fails `validate_manifest` immediately

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/build_set_manifest.py` | **NEW** — Main script with testable pure functions |
| `scripts/preflight_scan.py` | Added `source_date` to prompt draft |
| `scripts/menu.py` | Capability #12 `set-build` |
| `tests/test_build_set_manifest.py` | **NEW** — 27 tests |
| `tests/test_preflight_scan.py` | +2 tests for SOURCE_DATE |

---

## Tests

- **543 tests passing** (29 new in this release)
- **Ruff clean** (including `sopx/`)
- **Round-trip test**: generated manifest → `validate_manifest` → Chronology Gate

---

## Market Impact

| Capability | sop-extractor | Competitors |
|------------|:-------------:|:-----------:|
| Provenance loop | ✅ Automatic | ❌ Manual/nonexistent |
| Anti-data-fabrication | ✅ Strict rule | ⚠️ Trusts LLM |
| Idempotent merge | ✅ Preserves humans | ❌ Doesn't do |
| Fail-fast on incomplete data | ✅ Real validation | ❌ No validation |

**No other knowledge tool closes this loop automatically.**

---

## Breaking Changes

None. This is an additive feature.

---

## Deprecations

None.

---

## Upgrade

```bash
pip install -e ".[ingest]"
```

---

## Complete Usage Example

```bash
# 1. Ingest videos
sopx ingest https://youtube.com/watch?v=vid1
sopx ingest https://youtube.com/watch?v=vid2

# 2. Build manifest (NEW)
sopx set-build ./my-set --from-outputs output/

# Output:
#   Set: my-set  (2 members)
#   ✓ src vid001   2024-01-15  seq 1   [ingested]
#   ✓ src vid002   2024-03-20  seq 2   [ingested]
#   → Next: sopx validate ./my-set

# 3. Validate
sopx validate ./my-set

# 4. Extract skills
sopx scan output/vid001/transcript.srt --emit-prompt
# Prompt now includes: SOURCE_DATE = 2024-01-15 [measured from ingestion]
```

---

## Acknowledgments

Thanks to the reviewing engineer who identified 2 critical issues:
1. Reimplemented validator that diverged from the real one
2. SOURCE_DATE never actually being populated

Both fixed before merge.

---

## Next Steps

- v1.6.0: Batch channel ingestion (process entire playlists)
- v1.7.0: Frame extraction with VLM (visual analysis)
- v2.0.0: Teach Mode (Phase 1)
