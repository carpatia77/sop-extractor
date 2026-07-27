# POS — Point of Situation

> Atualizado: 2026-07-27 (sessão completa) | Versão: 3.0.0

---

## Resumo Executivo

**Conclusão geral: ~78%** (era 72% no POS anterior desta sessão, 65% no POS original)

### Ganhos desta sessão (4 commits)

| Commit | Mudança | Impacto |
|--------|---------|---------|
| `6c334a5` | Camada 4 ativa por padrão | Embeddings sempre contribuem, não só como fallback |
| `6c334a5` | T2 fechado (context-overlap) | Stoplist `_GENERIC_WORDS` extraída, docstrings atualizadas |
| `2c4fa9f` | Engine v1+v2 integram semantic_guard | match_layer + semantic_issues no output/history |
| `2c4fa9f` | 18 testes de integração sf_matcher | Camada 4 contribuição, deduplicação, engine flow |
| `82f26a8` | 34 testes E2E pipeline completo | sf_matcher → drift → semantic → depth → engine |
| `0957b13` | Cache em disco 2 tiers | memory + disk (~/.cache/sopx/embeddings/), 9 testes |

### Números da sessão

- **Testes**: 1033 → 1094 (+61)
- **Commits**: 4 na main
- **Linhas adicionadas**: ~900 (código + testes)
- **Arquivos modificados**: 5 (sf_matcher, sf_embeddings, semantic_guard, engine, engine_v2)
- **Arquivos criados**: 3 (test_sf_matcher_integration, test_chavruta_e2e, POS.md)

---

## Status por Fase

### Fase 1 — MVP (Extração): 92%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Preflight Scan | ✅ Pronto | 54 | PT-BR, layout conciso |
| Extract (SKILL.md) | ✅ Pronto | 137 | book_to_skill parser |
| Determinism Score | ✅ Pronto | — | Integrado no pipeline |
| 7 Validators | ✅ Prontos | 93 | coherence, evolution, arch, manifest, run_report, concept_presence, review_gate |
| Ingestão (Fase 0) | ✅ Pronto | 67 | yt-dlp + faster-whisper, CPU local |
| Provenance Loop | ✅ Pronto | 29 | build_set_manifest.py |
| LLM Router | ⏸️ Deferido | — | subprocess escolhido (trade-off consciente) |
| Wizard (GUI) | ✅ Pronto | 19 | Workflow interativo guiado |

### Fase 2 — Ensino: 88%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Semantic Field | ✅ Pronto | 45+20 | Extração + export (GraphML, JSON-LD, LightRAG) |
| Evidence Ledger | ✅ Pronto | 34 | Proveniência por claim |
| Refutation Chain | ✅ Pronto | 43 | strongest_alternative |
| Emerging Questions | ✅ Pronto | — | Detecta lacunas/tensões |
| Teach Mode (6 sessões) | ✅ Pronto | 29 | Método Hebraico, CLI funcional |
| validate_semantic_field | ⚠️ Parcial | — | Validador existe mas incompleto |
| F1 Scoring | ❌ Não iniciado | — | Pareto score 2.60 |

### Fase 3 — Escala: 58%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Cross-Analysis | ✅ Pronto | 24 | Consolida N vídeos em 1 graph |
| Batch Ingestion | ⚠️ Parcial | 67 | Single-video OK, batch canal não testado |
| VLM (análise visual) | ❌ Não iniciado | — | Pareto score 3.00 |
| Hardware Detection | ✅ Pronto | 25 | Auto-detect CPU/RAM, batch sizing |

### Fase 4 — Polimento: 65% (era 45%)

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Camada 4 (Embeddings) | ✅ **Pronto** | 27+31+9 | **Ativa por padrão + cache disco 2 tiers** |
| Semantic Guard | ✅ Pronto | 28 | 6 rounds, stoplist 60+ termos, T2 fechado |
| Chavruta Engine v1 | ✅ **Pronto** | 19+34 | **Integrado: semantic_guard + match_layer** |
| Chavruta Engine v2 | ✅ **Pronto** | 19+34 | **Integrado: evidence-backed + repetition detection** |
| sf_matcher | ✅ **Pronto** | 25+18 | **4 camadas ativas, testes de integração** |
| E2E Tests | ✅ **Pronto** | **34** | **Pipeline completo testado** |
| Disk Cache | ✅ **Pronto** | **9** | **2 tiers: memory + ~/.cache/sopx/embeddings/** |
| Docs | ⚠️ Parcial | — | Architecture, plans, POS — README incompleto |
| Stress Tests | ✅ Pronto | — | GURPS (23n) + QuantGuild (72n) |

---

## Pipeline Chavruta — Arquitetura Final

```
User response
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  sf_matcher (4 camadas)                              │
│  1. Exact ID  →  2. Substring  →  3. Salient  →  4. Embeddings
│                                                     │
│  Output: matched_node + match_layer                  │
└──────────────────────┬──────────────────────────────┘
                       │
    ▼                  ▼
┌──────────────┐  ┌──────────────────────┐
│ drift_detector│  │ semantic_guard        │
│              │  │ (type confusion,      │
│ (negation,   │  │  definition drift,    │
│  challenge,  │  │  scope expansion)     │
│  coverage)   │  │                      │
└──────┬───────┘  └──────────┬───────────┘
       │                     │
       ▼                     ▼
┌─────────────────────────────────────────────────────┐
│  depth_tracker (1-7)                                 │
│  Superficial → Compreensão → Análise → Síntese →    │
│  Avaliação → Criatividade → Meta-cognição            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  engine / engine_v2                                  │
│  - Gera challenge baseado no depth                   │
│  - Cita evidência (ev-ID, locator)                   │
│  - Detecta repetição (v2)                            │
│  - History + session summary                         │
│                                                     │
│  Output: { depth, challenge, match_layer,            │
│            semantic_issues, anchor_used }             │
└─────────────────────────────────────────────────────┘
```

**Todos determinísticos. Todos grounded no grafo. Zero alucinação por construção.**

---

## CLI — Capacidades (15/15)

| # | Comando | Status | Descrição |
|---|---------|--------|-----------|
| 1 | `scan` | ✅ | Pre-flight scan (PT-BR) |
| 2 | `extract` | ✅ | Hand-off para agent |
| 3 | `validate` | ✅ | 7 validadores determinísticos |
| 4 | `coherence` | ✅ | Auditoria single source |
| 5 | `evolution` | ✅ | Auditoria de Set |
| 6 | `blackhat` | ✅ | Reverse-engineering audit |
| 7 | `merge-arch` | ✅ | Merge multi-part arch docs |
| 8 | `determinism` | ✅ | Score determinístico |
| 9 | `view` | ✅ | Render HTML |
| 10 | `summary` | ✅ | Run log |
| 11 | `ingest` | ✅ | Video/URL → transcript |
| 12 | `set-build` | ✅ | Build manifest from metadata |
| 13 | `compile` | ✅ | Knowledge compilation |
| 14 | `teach` | ✅ | 6 sessões Método Hebraico |
| 15 | `wizard` | ✅ | Workflow guiado interativo |

---

## Codebase

| Módulo | Linhas | Descrição |
|--------|--------|-----------|
| `scripts/` | 9.320 | Core (validators, scan, compile, teach, wizard) |
| `sopx/` | 2.184 | Ingestion pipeline |
| `scripts/chavruta/` | 2.075 | Chavruta engine v1/v2, Semantic Guard, Camada 4, sf_matcher |
| `book_to_skill/` | 1.593 | Parser upstream (MIT) |
| `tests/` | 12.850 | 1094 testes |
| **Total** | **28.022** | |

### Testes por componente

| Componente | Testes | Arquivo |
|------------|--------|---------|
| book_to_skill | 137 | test_book_to_skill.py |
| compile | 70 | test_compile.py |
| ingestion | 67+18 | test_stress_ingestion + test_ingest_adapters |
| preflight_scan | 54 | test_preflight_scan.py |
| semantic_field | 45+20 | test_semantic_field + test_semantic_field_export |
| refutation_chain | 43 | test_refutation_chain.py |
| evidence_ledger | 34 | test_evidence_ledger.py |
| **E2E pipeline** | **34** | **test_chavruta_e2e.py** |
| teach_mode | 29 | test_teach_mode.py |
| build_set_manifest | 29 | test_build_set_manifest.py |
| semantic_guard | 28 | test_semantic_guard.py |
| **sf_embeddings (disk cache)** | **27** | **test_sf_embeddings.py** |
| review_gate | 26 | test_review_gate.py |
| sf_matcher | 25 | test_sf_matcher.py |
| hardware | 25 | test_hardware.py |
| cross_analysis | 24 | test_cross_analysis.py |
| drift_detector | 23 | test_drift_detector.py |
| chavruta_eval | 21 | test_chavruta_eval.py |
| validate_architecture | 20 | test_validate_architecture_audit.py |
| menu | 19 | test_menu.py |
| extract_frames | 19 | test_extract_frames_at_timestamps.py |
| chavruta_engine | 19 | test_chavruta_engine.py |
| **sf_matcher integration** | **18** | **test_sf_matcher_integration.py** |

---

## Cache de Embeddings (Camada 4)

```
Tier 1: In-memory   → dict, FIFO 8 entries, ~0ms
Tier 2: Disk        → ~/.cache/sopx/embeddings/, persiste restarts
Tier 3: Compute     → model.encode(), ~2-5s para SFs grandes
```

**Fluxo:** memory → disk → compute → store both tiers

**Arquivos por SF:** `{hash}.npy` (embeddings) + `{hash}.json` (metadata)

**API:** `embed_sf()`, `match_by_embedding()`, `clear_disk_cache()`, `disk_cache_size()`

---

## Próximos Passos (Pareto)

### Prioridade Alta (fecham o projeto)

| # | Item | Pareto Score | Esforço | Status |
|---|------|-------------|---------|--------|
| 1 | validate_semantic_field | — | ~2d | ⚠️ Gap Fase 2 |
| 2 | Batch ingestion test (canal inteiro) | — | ~1d | ⚠️ Não testado |
| 3 | README refresh | — | ~0.5d | ⚠️ Desatualizado |
| 4 | CHANGELOG v3.1 | — | ~0.5d | Novos features |

### Prioridade Média (diferenciação)

| # | Item | Pareto Score | Esforço | Status |
|---|------|-------------|---------|--------|
| 5 | F1 Scoring automatizado | 2.60 | ~3d | ❌ Não iniciado |
| 6 | VLM integration | 3.00 | ~5d | ❌ Não iniciado |
| 7 | Cross-model audit (embeddings) | — | ~1d | ⏸️ Adiado |

### Prioridade Baixa (nice-to-have)

| # | Item | Pareto Score | Esforço | Status |
|---|------|-------------|---------|--------|
| 8 | LLM Router | 3.25 | ~4d | ⏸️ Deferido |
| 9 | Node2vec | — | ~3d | ❌ Não iniciado |
| 10 | Batch channel (Fase 0 escala) | — | ~5d | ❌ Não iniciado |

---

## Posicionamento Competitivo

| vs | Diferencial | Moat |
|----|-------------|------|
| Gemini Notebook | Machine-consumable vs human summaries | ✅ Unique |
| LightRAG/Cognee | Compilation vs retrieval | ✅ Unique |
| Matt Pocock /teach | 6 sessões + Chavruta + anti-hallucination | ⚠️ Parcial |
| Qualquer RAG | "RAG indexa prateleira; isso domina a espinha" | ✅ Unique |

**Quadrante único confirmado:** Compilation + Machine-consumable + Anti-hallucination por construção.

---

## Regras Operacionais

1. **Measure, don't assert** — evidência antes de claims
2. **Keep SKILL.md lean** — spec do conversor, não chover
3. **Never ship raw book text** — sintetizar, nunca reproduzir
4. **Conventional Commits** — feat/fix/docs/chore/test/ci
5. **Three Strikes** — 3 falhas consecutivas → investigar fonte
6. **Human QA gate** — validate_all.py verde + eyeball
7. **Stamp provenance** — run.json antes de publicar
8. **Cross-model audits** — extrair em um, auditar em outro
9. **Branch + PR mandatory** — nunca push direto na main

---

## Changelog desta sessão

```
2026-07-27  0957b13  feat: disk cache for Camada 4 embeddings — 2-tier persistence
2026-07-27  82f26a8  test: 34 E2E tests for complete Chavruta pipeline
2026-07-27  2c4fa9f  feat: Chavruta Engine integrates Camada 4 + semantic guard + 18 integration tests
2026-07-27  6c334a5  feat: Camada 4 active by default + T2 closure + POS update
```
