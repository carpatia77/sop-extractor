# POS — Point of Situation

> Atualizado: 2026-07-29 (sessão completa) | Versão: 3.1.0

---

## Resumo Executivo

**Conclusão geral: ~78%** (era 74% — web console + BYOK + fixes + cyberpunk UI)

### Ganhos desta sessão

| Feature | Commits | Impacto |
|---------|---------|---------|
| validate_semantic_field completo | `8c6d59c`, `5ae8052`, `ff13b26` | evidence_id gate (scoped), enum {used_in,supports,requires,references}, standalone script, validate_all integration |
| Pipeline end-to-end | `c8377cf` | `--compile` flag encadeia ingest+compile |
| Ingest paralelo | `42e21e1` | `--workers N`, resume automático, ETA em tempo real |
| `sopx run` — cola o link | `291bcfe`, `1169c21` | Auto-detect: video/playlist/audio/livro/arquivo local |
| Web console | `8ec3259`, `db3ad13`, `1bd7c36` | Upload drag-drop, console SSE live, 4 abas resultado cyberpunk |
| BYOK genérico | `b7659e8`, `0ce7f08`, `fbc8f4b`, `cb1db63` | Qualquer API key (Anthropic, OpenAI, Nvidia, Gemini, Minimax, MiMo, Groq, Ollama, DeepSeek) |
| PDF extraction | `9f8ddd8` | pdfplumber para leitura de PDFs |
| Parse fix | `695aeb0` | Aceita ### e #### headers, bullets * e - |
| Cache_key fix | `40b19fb` | filepath == input_root não gera mais `.` como key |
| Graph cyberpunk | `7431477` | Glow neon, drag, grid, tema xHAL2049 |
| Incidentes | `0157d6f` | 6 incidentes documentados em WEB_CONSOLE_INCIDENTS.md |

### Números da sessão

- **Testes**: 1094 → 1108 (+14)
- **Commits**: 16 na main
- **Arquivos criados**: 3 (run.py, web_server.py, validate_semantic_field.py)
- **Arquivos modificados**: ~15 (compile.py, semantic_field.py, ingest.py, menu.py, wizard.py, README.md, etc.)

---

## Status por Fase

### Fase 1 — MVP (Extração): 95%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Preflight Scan | ✅ Pronto | 54 | PT-BR, layout conciso |
| Extract (SKILL.md) | ✅ Pronto | 137 | book_to_skill parser |
| Determinism Score | ✅ Pronto | — | Integrado no pipeline |
| 7 Validators | ✅ Prontos | 93 | coherence, evolution, arch, manifest, run_report, concept_presence, review_gate |
| Ingestão (Fase 0) | ✅ Pronto | 67+6 | yt-dlp + faster-whisper, batch playlist, workers paralelos |
| Provenance Loop | ✅ Pronto | 29 | build_set_manifest.py |
| LLM Router | ⏸️ Deferido | — | BYOK como alternativa funcional |
| Wizard (GUI) | ✅ Pronto | 19 | Workflow interativo + playlist + compile |
| **`sopx run`** | ✅ **Novo** | — | Auto-detect URL/file, ingest+compile chain |
| **`sopx web`** | ✅ **Novo** | — | Web console com upload, console live, 4 abas |

### Fase 2 — Ensino: 90%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Semantic Field | ✅ Pronto | 45+20+7 | Extração + export (GraphML, JSON-LD, LightRAG, HTML cyberpunk) |
| Evidence Ledger | ✅ Pronto | 34 | Proveniência por claim |
| Refutation Chain | ✅ Pronto | 43 | strongest_alternative |
| Emerging Questions | ✅ Pronto | — | Detecta lacunas/tensões |
| Teach Mode (6 sessões) | ✅ Pronto | 29 | Método Hebraico, CLI funcional |
| validate_semantic_field | ✅ Pronto | 55+ | evidence_id gate, standalone script, integração validate_all |
| F1 Scoring | ❌ Não iniciado | — | Pareto score 2.60 |

### Fase 3 — Escala: 68%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Cross-Analysis | ✅ Pronto | 24 | Consolida N vídeos em 1 graph |
| Batch Ingestion | ✅ Pronto | 67+6 | `--playlist --compile`, `--workers N`, resume automático |
| VLM (análise visual) | ❌ Não iniciado | — | Pareto score 3.00 |
| Hardware Detection | ✅ Pronto | 25 | Auto-detect CPU/RAM, batch sizing |
| **PDF extraction** | ✅ **Novo** | — | pdfplumber para PDFs via `sopx run` |

### Fase 4 — Polimento: 72%

| Componente | Status | Testes | Última mudança |
|------------|--------|--------|----------------|
| Camada 4 (Embeddings) | ✅ Pronto | 27+31+9 | Fallback gate + cache disco 2 tiers |
| Semantic Guard | ✅ Pronto | 28 | 6 rounds, stoplist 60+ termos |
| Chavruta Engine v1 | ✅ Pronto | 19+34 | Integrado: semantic_guard + match_layer |
| Chavruta Engine v2 | ✅ Pronto | 19+34 | Integrado: evidence-backed + repetition detection |
| sf_matcher | ✅ Pronto | 25+18 | 4 camadas, Camada 4 como fallback |
| E2E Tests | ✅ Pronto | 34 | Pipeline completo testado |
| Disk Cache | ✅ Pronto | 9 | 2 tiers: memory + disk |
| Docs | ✅ Pronto | — | README atualizado, CHANGELOG v3.1, POS atualizado, incident log |
| Stress Tests | ✅ Pronto | — | GURPS + QuantGuild |
| **Web Console** | ✅ **Novo** | — | Cyberpunk xHAL2049, drag-drop, console SSE, 4 abas |
| **BYOK** | ✅ **Novo** | — | Qualquer API key, settings page, presets |
| **Graph Cyberpunk** | ✅ **Novo** | — | Glow neon, drag interativo, grid background |

---

## CLI — Capacidades (18/18)

| # | Comando | Status | Descrição |
|---|---------|--------|-----------|
| 0 | `run` | ✅ **Novo** | Cola o link, auto-detect, ingest+compile |
| 1 | `scan` | ✅ | Pre-flight scan (PT-BR) |
| 2 | `extract` | ✅ | Hand-off para agent |
| 3 | `validate` | ✅ | 7+ validadores determinísticos |
| 4 | `coherence` | ✅ | Auditoria single source |
| 5 | `evolution` | ✅ | Auditoria de Set |
| 6 | `blackhat` | ✅ | Reverse-engineering audit |
| 7 | `merge-arch` | ✅ | Merge multi-part arch docs |
| 8 | `determinism` | ✅ | Score determinístico |
| 9 | `view` | ✅ | Render HTML |
| 10 | `summary` | ✅ | Run log |
| 11 | `ingest` | ✅ | Video/URL/playlist → transcript, `--workers`, `--compile` |
| 12 | `set-build` | ✅ | Build manifest from metadata |
| 13 | `compile` | ✅ | Knowledge compilation, PDF extraction, BYOK |
| 14 | `teach` | ✅ | 6 sessões Método Hebraico |
| 15 | `wizard` | ✅ | Workflow guiado + playlist |
| 16 | `web` | ✅ **Novo** | Web console (upload, console, resultado) |
| 17 | — | — | — |

---

## Codebase

| Módulo | Linhas | Descrição |
|--------|--------|-----------|
| `scripts/` | 10.800 | Core + run.py + web_server.py |
| `sopx/` | 2.300 | Ingestion pipeline |
| `scripts/chavruta/` | 2.075 | Chavruta engine v1/v2, Semantic Guard, Camada 4, sf_matcher |
| `book_to_skill/` | 1.593 | Parser upstream (MIT) |
| `tests/` | 13.100 | 1108 testes |
| **Total** | **~29.868** | |

---

## Cache de Embeddings (Camada 4)

```
Tier 1: In-memory   → dict, FIFO 8 entries, ~0ms
Tier 2: Disk        → ~/.cache/sopx/embeddings/, persiste restarts
Tier 3: Compute     → model.encode(), ~2-5s para SFs grandes
```

**Fluxo:** memory → disk → compute → store both tiers

---

## Web Console — Arquitetura

```
Browser (localhost:8080)
    │
    ├── GET /                    → HTML (upload + console)
    ├── GET /settings            → HTML (BYOK: base_url + api_key + model)
    ├── POST /upload             → Salva arquivos, inicia pipeline
    ├── GET /progress/<sid>      → SSE (progresso em tempo real)
    ├── GET /results/<sid>/skill → Rendered MD (cyberpunk)
    ├── GET /results/<sid>/graph → semantic_field.html (cyberpunk)
    ├── GET /results/<sid>/summary → Dashboard (cyberpunk)
    ├── GET /results/<sid>/sf    → Semantic Field JSON (grupos)
    ├── GET /api/settings        → JSON settings
    └── POST /api/settings       → Salva settings
```

**Pipeline:** upload → `sopx run` → compile.py → BYOK API → output → botões resultado

---

## Próximos Passos (Pareto)

### Prioridade Alta

| # | Item | Esforço | Status |
|---|------|---------|--------|
| 1 | Batch ingestion test real-world (canal 500 vídeos) | ~1d | ⚠️ Requer URL específica |
| 2 | F1 Scoring automatizado | ~3d | ❌ Não iniciado |

### Prioridade Média

| # | Item | Esforço | Status |
|---|------|---------|--------|
| 3 | VLM integration (imagens/screenshots) | ~5d | ❌ Não iniciado |
| 4 | Cross-model audit (embeddings) | ~1d | ⏸️ Adiado |
| 5 | Graph: edges cross-principle (contradicts real) | ~2d | ❌ Requer detecção de contradição |

### Prioridade Baixa

| # | Item | Esforço | Status |
|---|------|---------|--------|
| 6 | LLM Router (multiplexador de providers) | ~4d | ⏸️ Deferido |
| 7 | Node2vec | ~3d | ❌ Não iniciado |
| 8 | OpenTelemetry / tracing | ~2d | ❌ Não iniciado |

---

## Posicionamento Competitivo

| vs | Diferencial | Moat |
|----|-------------|------|
| Gemini Notebook | Machine-consumable vs human summaries | ✅ Unique |
| LightRAG/Cognee | Compilation vs retrieval | ✅ Unique |
| Matt Pocock /teach | 6 sessões + Chavruta + anti-hallucination | ✅ Confirmado |
| Qualquer RAG | "RAG indexa prateleira; isso domina a espinha" | ✅ Unique |
| Qualquer extração | BYOK + Web Console + Cyberpunk UI | ✅ UX Differentiator |

**Quadrante único confirmado:** Compilation + Machine-consumable + Anti-hallucination + Web Console + BYOK.

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
2026-07-29  1bd7c36  feat: cyberpunk layout para Skill, Semantic Field, Summary
2026-07-29  7431477  feat: graph cyberpunk — tema xHAL2049, glow, drag, grid
2026-07-29  40b19fb  fix: cache_key bug + web_server glob patterns
2026-07-29  695aeb0  fix: parse_compilation — aceita ### e #### headers, bullets * e -
2026-07-29  cb1db63  fix: API URL flexivel — evita duplicar /v1, preset Nvidia corrigido
2026-07-29  fbc8f4b  feat: presets Gemini, Minimax, MiMo substituem Together
2026-07-29  0ce7f08  feat: BYOK generico — qualquer API OpenAI-compativel
2026-07-29  b7659e8  feat: BYOK — web console com settings para API key
2026-07-29  9f8ddd8  fix: compile.py extrai texto de PDF via pdfplumber
2026-07-29  db3ad13  fix: web_server remove --compile flag
2026-07-29  8ec3259  feat: web console — xHAL2049 banner, upload, console live
2026-07-29  291bcfe  feat: sopx run — cola o link, eu resolvo
2026-07-29  42e21e1  feat: ingest paralelo — workers, resume, ETA
2026-07-29  c8377cf  feat: pipeline end-to-end playlist → ingest → compile
2026-07-28  695aeb0  fix: parse_compilation — ### e #### headers
2026-07-28  ff13b26  fix: remover contradicts self-loop
2026-07-28  5ae8052  fix: require_evidence scoped + badge 1108
2026-07-28  8c6d59c  feat: validate_semantic_field completo + README + CHANGELOG v3.1.0
```
