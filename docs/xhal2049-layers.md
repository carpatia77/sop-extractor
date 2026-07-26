# xHAL2049 — Layers Técnicas

> Divisão técnica e profissional para organizar a engenharia de backend.

## Visão Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  LAYER 1: INFRAESTRUTURA (fundação)                             │
│  • Config manager (~/.xhal2049/config.yaml)                     │
│  • LLM Router (roteamento por tarefa/custo)                     │
│  • Cost Estimator (estimativa antes de processar)                │
│  • Cache Manager (não reprocessa)                                │
│  • Logger + run_manifest                                        │
│  Dependências: yaml, hashlib, json                              │
│  Responsável: infra-team                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 2: INGESTÃO (entrada de dados)                           │
│  • yt-dlp adapter (download de vídeos)                          │
│  • ffmpeg adapter (extração áudio + frames)                     │
│  • whisper adapter (transcrição → SRT)                          │
│  • Batch processor (paralelismo + progresso)                    │
│  • Deduplication (não reprocessa)                                │
│  Dependências: yt-dlp, ffmpeg, faster-whisper                   │
│  Responsável: ingest-team                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 3: ANÁLISE (processamento inteligente)                   │
│  • Preflight Scanner (detecta tipo, formato, duração)           │
│  • VLM Analyzer (descreve frames visualmente)                   │
│  • NERRE Extractor (entidades + relações em JSON)               │
│  • Concept Extractor (conceitos-chave do texto)                 │
│  • Entity Normalizer (normalização de termos)                   │
│  Dependências: LLM APIs (via LLM Router)                        │
│  Responsável: analysis-team                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 4: EVIDÊNCIA (proveniência + qualidade)                  │
│  • Evidence Ledger (proveniência por claim)                     │
│  • Epistemic Classifier (certo/provável/suposição/não_sei)      │
│  • Refutation Builder (strongest_alternative + disconfirming)   │
│  • Evidence Validator (gates de evidência)                      │
│  Dependências: Layer 3                                          │
│  Responsável: evidence-team                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 5: EXTRAÇÃO (geração de artefatos)                       │
│  • Skill Generator (SKILL.md, chapters, glossário)              │
│  • Semantic Field Builder (conceitos + relações)                │
│  • Emerging Questions Generator (lacunas + tensões)             │
│  • Author Decisions Recorder (ADRs do autor)                    │
│  • Concept Graph Builder (nós + arestas)                        │
│  Dependências: Layers 3-4                                       │
│  Responsável: extraction-team                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 6: VALIDAÇÃO (qualidade determinística)                  │
│  • Validators existentes (7 scripts)                            │
│  • Semantic Field Validator (gates novos)                        │
│  • Evidence Ledger Validator                                    │
│  • F1 Scoring Engine                                            │
│  • validate_all.py (orquestra tudo)                             │
│  Dependências: Layer 5                                          │
│  Responsável: validation-team                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 7: CROSS-ANALYSIS (consolidação multi-vídeo)             │
│  • Multi-video Consolider (N → 1 graph)                         │
│  • Theme Detector (temas recorrentes)                           │
│  • Evolution Tracker (mudança temporal)                         │
│  • Gold Extractor (conceitos únicos/raros)                      │
│  • Link Predictor (node2vec + RF)                               │
│  Dependências: Layers 4-5                                       │
│  Responsável: cross-analysis-team                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 8: EXPORT (formatos de saída)                            │
│  • GraphML Exporter                                             │
│  • JSON-LD Exporter                                             │
│  • LightRAG/Cognee Adapter                                     │
│  • HTML Viewer (render_skill_viewer.py)                         │
│  • Markdown Renderer (semantic_field.md)                        │
│  Dependências: Layers 5-7                                       │
│  Responsável: export-team                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 9: ENSINO (Debate Socrático)                              │
│  • Session Manager (6 sessões stateful)                         │
│  • Task Contract Builder (Sessão 1)                             │
│  • ZPD Calculator (Zone of Proximal Development)                │
│  • Storage Strength Tracker (Fluency vs Retenção)               │
│  • Application Logger (Sessão 6)                                │
│  Dependências: Layers 5-6                                       │
│  Responsável: teaching-team                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 10: CHAVRUTA (debate + profundidade)                     │
│  • Debate Engine (pergunta desafiadora)                          │
│  • Depth Tracker (1-7, analogia xadrez)                         │
│  • SF Validator (ancora no Semantic Field)                       │
│  • Drift Detector (não sai do escopo)                           │
│  • Depth Reporter (métricas de profundidade)                    │
│  Dependências: Layers 5+9                                       │
│  Responsável: chavruta-team                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 11: CLI (interface do usuário)                           │
│  • Comandos: ingest, teach, graph, extract-gold                 │
│  • Menu interativo (menu.py)                                    │
│  • Config UI (sopx config)                                      │
│  • Progress UI (barras de progresso)                            │
│  • Output formatting (PTY colors, tables)                       │
│  Dependências: todas as layers                                  │
│  Responsável: cli-team                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Mapa de dependências

```
LAYER 11 (CLI)
    ├── LAYER 10 (Chavruta) → LAYER 9 → LAYER 5 → LAYER 4 → LAYER 3
    ├── LAYER 8 (Export) → LAYER 7 → LAYER 5
    ├── LAYER 6 (Validação) → LAYER 5
    ├── LAYER 2 (Ingestão) → LAYER 1
    └── LAYER 1 (Infraestrutura)
```

---

## Ordem de implementação

| Fase | Layer | Nome | Dependências | Esforço |
|------|-------|------|-------------|---------|
| 0 | 1 | Infraestrutura | nenhuma | 3-5 dias |
| 1 | 2 | Ingestão | Layer 1 | 5-7 dias |
| 2 | 3 | Análise | Layer 1 | 5-7 dias |
| 3 | 4 | Evidência | Layer 3 | 3-4 dias |
| 4 | 5 | Extração | Layers 3-4 | 5-7 dias |
| 5 | 6 | Validação | Layer 5 | 3-4 dias |
| 6 | 7 | Cross-Analysis | Layers 4-5 | 5-7 dias |
| 7 | 8 | Export | Layers 5-7 | 2-3 dias |
| 8 | 9 | Ensino | Layers 5-6 | 5-7 dias |
| 9 | 10 | Chavruta | Layers 5+9 | 4-5 dias |
| 10 | 11 | CLI | todas | 3-5 dias |

**Total:** 42-60 dias (1 pessoa) | 14-20 dias (3 pessoas) | 7-10 dias (6 pessoas)

---

## Equipe sugerida

| Cenário | Pessoas | Foco |
|---------|---------|------|
| **Mínimo (1 pessoa)** | 1 fullstack | Layers 1-6 + 11 |
| **Enxuto (3 pessoas)** | 3 | Infra+Ingestão | Análise+Extração | Validação+CLI |
| **Completo (6+)** | 6+ | 1 pessoa por layer |

---

## Diretórios por layer

```
xhal2049/
├── config/          # Layer 1
├── ingest/          # Layer 2
├── analysis/        # Layer 3
├── evidence/        # Layer 4
├── extraction/      # Layer 5
├── validation/      # Layer 6
├── cross_analysis/  # Layer 7
├── export/          # Layer 8
├── teaching/        # Layer 9
├── chavruta/        # Layer 10
├── cli/             # Layer 11
├── schemas/         # Schemas JSON
├── tests/           # Testes por layer
└── docs/            # Documentação
```
