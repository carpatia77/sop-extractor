# POS — Point of Situation

> Atualizado: 2026-07-27 | Último POS: 2026-07-26

---

## Resumo Executivo

**Conclusão geral: ~72%** (era 65% no POS anterior)

Ganhos desde o último POS:
- Camada 4 (embeddings) ativada por padrão (+5%)
- Semantic Guard finalizado (6 rounds, stoplist 60+ termos)
- T2 (context-overlap) fechado
- 1033 testes passando, ruff clean

---

## Status por Fase

### Fase 1 — MVP (Extração): 90%

| Componente | Status | Testes | Notas |
|------------|--------|--------|-------|
| Preflight Scan | ✅ Pronto | 54 | PT-BR, todos os formatos |
| Extract (SKILL.md) | ✅ Pronto | 137 | book_to_skill parser |
| Determinism Score | ✅ Pronto | — | Integrado |
| 7 Validators | ✅ Prontos | 93 | coherence, evolution, arch, manifest, run_report, concept_presence, review_gate |
| Ingestão (Fase 0) | ✅ Pronto | 67 | yt-dlp + faster-whisper, CPU local |
| Provenance Loop | ✅ Pronto | 29 | build_set_manifest.py |
| LLM Router | ⏸️ Deferido | — | subprocess escolhido (consciente) |
| Wizard (GUI) | ✅ Pronto | 19 | Workflow interativo guiado |

### Fase 2 — Ensino: 85%

| Componente | Status | Testes | Notas |
|------------|--------|--------|-------|
| Semantic Field | ✅ Pronto | 45+20 | Extração + export (GraphML, JSON-LD, LightRAG) |
| Evidence Ledger | ✅ Pronto | 34 | Proveniência por claim |
| Refutation Chain | ✅ Pronto | 43 | strongest_alternative |
| Emerging Questions | ✅ Pronto | — | Detecta lacunas/tensões |
| Teach Mode (6 sessões) | ✅ Pronto | 29 | Método Hebraico, CLI funcional |
| validate_semantic_field | ⚠️ Parcial | — | Validador existe mas incompleto |
| F1 Scoring | ❌ Não iniciado | — | Pareto score 2.60 |

### Fase 3 — Escala: 55% (era 35%)

| Componente | Status | Testes | Notas |
|------------|--------|--------|-------|
| Cross-Analysis | ✅ Pronto | 24 | Consolida N vídeos em 1 graph |
| Batch Ingestion | ⚠️ Parcial | 67 | Single-video OK, batch canal não testado |
| VLM (análise visual) | ❌ Não iniciado | — | Pareto score 3.00 |
| Hardware Detection | ✅ Pronto | 25 | Auto-detect CPU/RAM, batch sizing |

### Fase 4 — Polimento: 45% (era 30%)

| Componente | Status | Testes | Notas |
|------------|--------|--------|-------|
| Camada 4 (Embeddings) | ✅ Pronto | 18+31 | **Ativada por padrão** (antes era fallback) |
| Semantic Guard | ✅ Pronto | 28 | 6 rounds, stoplist 60+ termos, T2 fechado |
| Chavruta Engine | ✅ Pronto | 21+25 | sf_matcher 4 camadas |
| E2E Tests | ⚠️ Parcial | — | Stress tests GURPS/QuantGuild |
| Docs | ⚠️ Parcial | — | Architecture, plans, mas README incompleto |
| Stress Tests | ✅ Pronto | — | GURPS (23n) + QuantGuild (72n) |

---

## CLI — Capacidades

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

**15/15 cap funcionais.** Nenhum placeholder.

---

## Codebase

| Módulo | Linhas | Descrição |
|--------|--------|-----------|
| `scripts/` | 9.320 | Core (validators, scan, compile, teach, wizard) |
| `sopx/` | 2.184 | Ingestion pipeline |
| `scripts/chavruta/` | 1.920 | Chavruta engine, Semantic Guard, Camada 4 |
| `book_to_skill/` | 1.593 | Parser upstream (MIT) |
| **Total** | **15.017** | |
| `tests/` | 1033 testes | ruff clean |

---

## Últimas Mudanças (desde último POS)

| Data | Mudança | Impacto |
|------|---------|---------|
| 2026-07-27 | Camada 4 ativa por padrão | Embeddings sempre contribuem, não só como fallback |
| 2026-07-27 | T2 fechado (context-overlap) | Stoplist extraída como `_GENERIC_WORDS`, docstring atualizada |
| 2026-07-26 | Semantic Guard 6 rounds | Stoplist 60+ termos, ms/Hz categorização, vírgula parsing |
| 2026-07-26 | Camada 4 implementada | sf_embeddings.py (250 linhas), threshold 0.50 calibrado |
| 2026-07-26 | Stress tests | GURPS 23n + QuantGuild 72n, 4 vitórias exclusivas |

---

## Próximos Passos (Pareto)

### Prioridade Alta
1. **validate_semantic_field** — completar validador (Fase 2 gap)
2. **Batch ingestion test** — testar processamento de canal inteiro
3. **E2E test suite** — testes de ponta a ponta reais

### Prioridade Média
4. **F1 Scoring automatizado** — Pareto score 2.60
5. **VLM integration** — análise visual de frames (Pareto score 3.00)
6. **Docs refresh** — README, CHANGELOG v3.1

### Prioridade Baixa
7. **LLM Router** — manter deferido (subprocess funciona)
8. **Node2vec** — predição de links no concept graph

---

## Posicionamento Competitivo

| vs | Diferencial | Status |
|----|-------------|--------|
| Gemini Notebook | Machine-consumable (não humano) | ✅ Unique |
| LightRAG/Cognee | Compilation (não retrieval) | ✅ Unique |
| Matt Pocock /teach | 6 sessões + Chavruta + anti-hallucination | ⚠️ Parcial |
| Qualquer RAG | "RAG indexa prateleira; isso domina a espinha" | ✅ Unique |

**Quadrante único**: Compilation + Machine-consumable + Anti-hallucination por construção.

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
