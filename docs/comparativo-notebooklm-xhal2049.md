# Comparativo CLI/UX: sop-extractor (xHAL2049) vs Gemini Notebook

**Data**: 2026-07-24
**Perspectiva**: Engenheiro Fullstack — Engenharia Reversa de Sistemas
**Foco**: Capacidades CLI/UX, arquitetura de interacao, pipeline de dados, modelo de operacao

---

## 1. Visao de Arquitetura

| Dimensao | sop-extractor (xHAL2049) | Gemini Notebook |
|---|---|---|
| **Paradigma** | CLI pipeline deterministico + agent LLM | Web app com LLM conversacional |
| **Interface** | Terminal (TUI), interativa ou headless | Browser + mobile app |
| **Execucao** | Local (CPU/GPU) + Colab offload | 100% cloud (Google infra) |
| **Modelo de dados** | Arquivos no disco (SRT, JSON, MD) | Notebooks na cloud (Google Drive) |
| **Distribuicao** | pip install (`sopx`), open source Apache 2.0 | SaaS proprietario, Google account obrigatoria |
| **Custo de entrada** | Gratuito (BYOK — user paga APIs) | Free tier limitado -> Plus/Pro/Ultra pago |
| **Dependencia externa** | yt-dlp, ffmpeg, whisper (todos locais) | Google account, internet obrigatoria |
| **Offline** | Funcional (exceto YouTube URL) | Totalmente online |
| **API/Programabilidade** | 12 verbos CLI headless + pyproject.toml | Nenhuma API publica documentada |
| **Testabilidade** | 545 pytest, CI/CD, ruff lint | N/A (black box) |

---

## 2. Capacidades de Ingestao — Matriz Comparativa

| Fonte de dados | sop-extractor | Gemini Notebook |
|---|---|---|
| **PDF** | pypdf/pdftotext/pdfminer (fallback chain) | Upload direto |
| **EPUB** | ebooklib + stdlib fallback | Upload |
| **DOCX** | python-docx | Upload Word |
| **TXT/Plain text** | Direto | Upload ou paste |
| **Markdown** | Direto | Upload |
| **reStructuredText** | Direto | Nao suportado |
| **AsciiDoc** | Direto | Nao suportado |
| **HTML** | BeautifulSoup | Via URL (scraping) |
| **RTF** | Direto | Nao suportado |
| **MOBI/AZW** | Via Calibre | Nao suportado |
| **YouTube URL** | yt-dlp + whisper transcricao local | Transcricao via captions |
| **YouTube playlist/channel** | Batch ingestion (`--playlist`) | Apenas 1 video por vez |
| **Video local** | ffmpeg + whisper (GPU opcional) | Nao suportado |
| **Audio local** | whisper (local, hardware-adaptive) | Upload audio (transcription server-side) |
| **Google Docs** | Nao | Auto-sync com Drive |
| **Google Slides** | Nao | Ate 100 slides |
| **Google Sheets** | Nao | Ate 100k tokens |
| **Imagens** | Extracao de frames em timestamps | Upload (avif, bmp, gif, jpeg, png, webp...) |
| **CSV** | Nao | Upload |
| **PPTX** | Nao | Upload |
| **Web pages** | Nao (so via ingestao de video) | URL scraping |
| **Clipboard/Paste** | Nao | Texto direto |
| **Max. fontes** | Ilimitado (disco local) | 50 (free) -> 600 (Ultra) |
| **Tamanho max. por fonte** | Ilimitado | 500K palavras ou 200MB |

### Analise de Engenharia Reversa

**sop-extractor tem vantagem em:**
- Formatos tecnicos obscetos (RTF, MOBI, AsciiDoc, reST) — pipeline de fallback em cadeia
- Video local + transcricao offline — zero dependencia de cloud
- Batch de playlists/canais inteiros — processamento massivo
- Hardware-adaptive (detecta cores/RAM/GPU e ajusta batch_size/beam_size automaticamente)

**Gemini Notebook tem vantagem em:**
- Google Workspace nativo (Docs/Slides/Sheets auto-sync)
- Imagens multimodais (upload direto, analise visual)
- Web scraping de URLs genericas
- Clipboard paste (zero friction)
- Formatos de escrita (CSV, PPTX) — foco em consumption, nao extraction

---

## 3. Capacidades de Processamento/Analise

| Capacidade | sop-extractor | Gemini Notebook |
|---|---|---|
| **Classificacao automatica** | Pre-flight scan: technical/text + confidence scoring | Auto-labeling de fontes (5+ sources) |
| **Extracao de conceitos** | Conceitos, SOPs, principios fundamentais | Sumarizacao generica |
| **Mapa Semantico** | Planejado (Fase 1) | Mind Maps |
| **Grafo de Conceitos** | Planejado (Fase 1) | Nao |
| **Epistemic status** | Certo/provavel/suposicao/nao_sei por claim | Nao |
| **Determinism score** | % de procedimentos extraidos vs total | Nao |
| **Auditoria de coerencia** | Coherence audit (single source) | Nao |
| **Auditoria de evolucao** | Evolution audit (multi-source temporal) | Nao |
| **Auditoria de arquitetura (Blackhat)** | Reverse-engineering audit com seals [OBSERVED]/[INFERRED] | Nao |
| **Triage de conceitos** | Concept presence triage com scoring | Nao |
| **Proveniencia** | run.json, set_manifest.json, SHA256 hashes | Nao (apenas citations inline) |
| **Anti-hallucination deterministico** | 4 gates: Seal, Grounding, Intent, Non-Contamination | Nao (usa apenas prompt instruction) |
| **Cross-analysis (multi-video)** | Planejado (Fase 0.5) | Nao |
| **Gold extraction** | Planejado (Fase 0.5) | Nao |
| **Deep Research** | Nao | Agentic browsing de centenas de sites |
| **Fast Research** | Nao | Busca web/Drive integrada |
| **Chat conversacional** | Nao (CLI interativo mas nao LLM chat) | Chat com Gemini sobre fontes |
| **Flashcards/Quizzes** | Nao | Auto-gerados |
| **Relatorios** | Extraction summary com tokens/words | FAQ, study guide, briefing doc |
| **Data Tables** | Nao | Exportavel para Sheets |
| **Infographics** | Nao | Via Nano Banana Pro |
| **Slide Decks** | Nao | Via Nano Banana Pro |
| **Audio Overview (podcast)** | Nao | 2 hosts AI conversando |
| **Video Overview** | Nao | Slide-style + narracao AI |
| **Short Video (60s)** | Nao | Vertical format |
| **Code execution** | Local (Python scripts) | Cloud computer por notebook (Jul 2026) |

### Analise de Engenharia Reversa

**O gap fundamental**: sop-extractor e um **compilador de conhecimento** (extrai logica de decisao, SOPs, axiomas). Gemini Notebook e um **consumidor de conhecimento** (sumariza, apresenta, formate).

| Paradigma | sop-extractor | Gemini Notebook |
|---|---|---|
| **Input -> Output** | Documento -> Skill (decisao acionavel) | Documento -> Resumo/podcast/apresentacao |
| **Profundidade** | Decomposicao em primeiros principios + procedimentos | Superficie: sumario, listas, analogias |
| **Auditabilidade** | Cada claim tem evidence_id, epistemic status | Sem audit trail |
| **Reusabilidade** | Output e skill executavel por agent LLM | Output e artefato estatico (PDF/slide/audio) |

---

## 4. UX/Interface — Comparacao Tecnica

| Aspecto UX | sop-extractor | Gemini Notebook |
|---|---|---|
| **Modo de interacao** | Menu interativo (1-12, q) + headless args | Point-and-click GUI |
| **Pre-flight preview** | Deteccao automatica com confidence scoring | Upload direto sem analise previa |
| **Progress feedback** | tqdm bars + stage counters [1/4] + ETA | Loading spinners + web notifications |
| **Summary cards** | Unicode box-drawing (┌─ │ └─) | Flat UI |
| **Confidence icons** | ● (alta) ◐ (media) ○ (baixa) | Nao |
| **Status icons** | ✓✗⚠✅❌🔎 + emojis contextuais | Basicos (check/x) |
| **Change detection** | 🟢NEW 🔴REMOVED 🟡CHANGED ⚪UNCHANGED | Nao |
| **Error messages** | Accionaveis: "instale com: pip install X" | Genericos |
| **Dry-run mode** | `--dry-run` em set-build, frames | Nao |
| **Post-action prompts** | 4 escolhas apos ingestao (SOPs/Map/Graph/Keep) | Sem proximo passo guiado |
| **Batch progress** | "Video 1/5" com separators | Sem batch |
| **Cache UX** | "Cache hit — reutilizando output anterior" | Transparent (cloud) |
| **Routing recommendation** | "Local: ~24:36 -> Colab: ~0:21 (69x)" | Nao |
| **Multi-part handling** | Deteccao + confirmacao manual se tipos divergem | Nao |
| **Export** | SRT, TXT, JSON, HTML viewer, run.jsonl | Docs, Sheets, audio/video/podcast |
| **Sharing** | Nao (arquivos locais) | Private (50 users) / Public link |
| **Mobile** | CLI only | Android + iOS apps |
| **Localization** | PT-BR completo (mensagens, erros, labels) | 80+ idiomas |

---

## 5. Pipeline de Dados — Fluxo Tecnico

### sop-extractor (12 capabilities, pipeline aberto)

```
Input ──→ [scan] ──→ [extract] ──→ [validate] ──→ [audit] ──→ [view]
  │          │           │              │              │           │
  │     Pre-flight   Agent/LLM     5 validators   4 gates    HTML viewer
  │     Detection    Generation    (deterministic) (seal,     (dark theme)
  │     RE Candi-    SKILL.md      + concept       grounding,
  │     date detect                triage          intent,
  │                                                 non-contam)
  │
  └──→ [ingest] ──→ [set-build] ──→ [determinism] ──→ [summary]
         │              │                │                 │
    yt-dlp+whisper  Manifest      Score %           Token count
    Hardware adapt  builder       Per chapter        Regression
    Colab routing   Idempotent    JSON output        detection
```

### Gemini Notebook (features, painel centralizado)

```
Upload ──→ [Sources Panel] ──→ [Chat Panel] ──→ [Studio Panel]
  │              │                  │                  │
  │         Auto-label        Conversational     ┌─ Notes
  │         Source guide       Q&A               ├─ Audio Overview
  │         Summaries                             ├─ Video Overview
  │                                              ├─ Mind Maps
  │                                              ├─ Reports
  │                                              ├─ Flashcards/Quizzes
  │                                              ├─ Data Tables
  │                                              ├─ Infographics
  │                                              ├─ Slide Decks
  │                                              └─ Deep Research
  └──→ [Fast Research] ──→ Web/Drive sources ──→ Import
  └──→ [Deep Research] ──→ Agentic browsing ──→ Multi-page report
```

---

## 6. Modelo de Custo

| Aspecto | sop-extractor | Gemini Notebook |
|---|---|---|
| **Custo base** | $0 (open source) | Free tier (limitado) |
| **Custo de processamento** | $0 (local) ou $0 (Colab free tier) | $0 (incluso no plano) |
| **Custo de LLM (extracao)** | $0.04-0.22/video (routing inteligente) | Incluso (Gemini 3.5) |
| **Plano Plus** | N/A | Google AI Plus |
| **Plano Pro** | N/A | Google AI Pro |
| **Plano Ultra** | N/A | Google AI Ultra |
| **Enterprise** | N/A | Google Cloud (custom pricing) |
| **Hardware minimo** | 8GB RAM, CPU dual-core | Browser + internet |
| **GPU opcional** | Sim (T4 via Colab) | Nao (cloud GPU) |
| **Escalabilidade** | Linear (mais CPU = mais rapido) | Limitada por quotas de plano |
| **Custo para 1000 videos** | ~$40-220 (API routing) + $0 (local whisper) | N/A (nao suporta batch) |
| **Custo anual estimado (power user)** | $0-500 (APIs) | $200-600 (AI Pro/Ultra) |

---

## 7. Limites e Quotas

| Quota | sop-extractor | Gemini Notebook Free | Gemini Notebook Ultra |
|---|---|---|---|
| **Notebooks** | Ilimitado | 100/user | 500/user |
| **Fontes por notebook** | Ilimitado | 50/notebook | 600/notebook |
| **Chats/dia** | Ilimitado | 50/day | 5,000/day |
| **Audio Overviews/dia** | N/A | 3/day | 200/day |
| **Video Overviews/dia** | N/A | 3/day | 200/day |
| **Reports/dia** | Ilimitado (script) | 10/day | 1,000/day |
| **Flashcards/dia** | N/A | 10/day | 1,000/day |
| **Deep Research/dia** | N/A | 10/month | 200/day |
| **Processamento de video** | Ilimitado (local) | 1 video por vez | 1 video por vez |
| **Tamanho max. input** | Ilimitado | 500K palavras | 500K palavras |

---

## 8. Gap Analysis — O que cada um tem que o outro nao tem

### sop-extractor TEM, Gemini Notebook NAO TEM

| Capacidade | Impacto |
|---|---|
| **CLI headless / scripting** | Automacao, CI/CD, integracao em pipelines |
| **Batch playlist/channel** | Processamento massivo de canais YouTube inteiros |
| **Video local + transcricao** | Funciona sem internet, com qualquer video |
| **Hardware detection + routing** | Adapta automaticamente ao hardware disponivel |
| **Pre-flight scan com confidence** | Analise previa antes de commit custoso |
| **Determinism score** | Metrica objetiva da qualidade da extracao |
| **4 audit gates deterministico** | Anti-hallucination real (nao prompt-based) |
| **Epistemic status** | Cada claim tem status de certeza |
| **Proveniencia rastreavel** | run.json, SHA256, date_source labels |
| **Coherence + evolution audit** | Deteccao de contraddicoes e drift temporal |
| **Blackhat mode (RE audit)** | Reverse engineering com seals [OBSERVED]/[INFERRED] |
| **Concept presence triage** | Scoring de groundedness por conceito |
| **Change detection** | 🟢🔴🟡⚪ diffs entre runs |
| **Regression detection** | Alertas automaticos de queda de quality |
| **Dry-run mode** | Preview antes de commit |
| **Run log (JSONL)** | Historico append-only com metricas |
| **Cache per-stage** | Audio/SRT/output cached separadamente |
| **PT-BR nativo** | UX toda em portugues |
| **Offline-first** | Funciona 100% local |
| **Open source** | Auditar, modificar, self-host |
| **BYOK (bring your own key)** | Controle total sobre custos de LLM |
| **Export SRT subtitles** | Output utilizavel em editores de video |
| **Frame extraction** | Screenshots em timestamps deicticos |
| **Colab GPU notebook gerado** | Um-click para GPU gratuita |
| **Anti-ban yt-dlp** | UA rotation, rate limiting, retry com backoff |
| **Set manifest builder** | Metadados cross-source com sequence e date_source |

### Gemini Notebook TEM, sop-extractor NAO TEM

| Capacidade | Impacto |
|---|---|
| **GUI point-and-click** | Zero curva de aprendizado |
| **Mobile apps (Android/iOS)** | Uso em qualquer lugar |
| **Audio Overview (podcast)** | Formato de consumo passivo popular |
| **Video Overview** | Apresentacao visual automatica |
| **Short Video (60s vertical)** | Conteudo para redes sociais |
| **Mind Maps visuais** | Visualizacao grafica de relacoes |
| **Infographics** | Imagens de alta qualidade |
| **Slide Decks** | Apresentacoes prontas |
| **Flashcards/Quizzes** | Estudo ativo, repeticao espacada |
| **Data Tables exportaveis** | Dados estruturados -> Sheets |
| **Chat conversacional** | Q&A interativo com fontes |
| **Deep Research** | Browsing agentic de centenas de sites |
| **Fast Research** | Busca web/Drive integrada |
| **Google Workspace sync** | Auto-sync com Docs/Slides/Sheets |
| **Sharing publico/privado** | Colaboracao com links |
| **Usage analytics** | Metricas de uso por notebook |
| **Multi-idioma (80+)** | Internacionalizacao automatica |
| **Cloud computer por notebook** | Code execution server-side |
| **Auto-generated previews** | Artefatos iniciais ao adicionar fontes |
| **Embedding em Gemini app** | Integracao com ecossistema Google |

---

## 9. Moat Competitivo — Analise de Engenharia Reversa

### 5 Pontos de Diferenciacao Irreplicaveis (sop-extractor)

1. **Compilation > Extraction**: sop-extractor compila "o que e conhecido" (logica de decisao), nao extrai "o que existe" (entidades/relacoes). Gemini Notebook sumariza; sop-extractor transforma em skill acionavel.

2. **Epistemic Status obrigatorio**: Cada no/aresta do grafo carrega certo/provavel/suposicao/nao_sei. Nenhum outro projeto faz isso. Gemini Notebook nao tem conceito equivalente.

3. **Gates deterministicos anti-hallucination**: 4 validadores sequenciais (Seal, Grounding, Intent, Non-Contamination) bloqueiam publicacao sem evidence_id. Gemini usa apenas prompt instruction — zero garantia mecanica.

4. **Refutation chain**: Cada claim tem strongest_alternative + falsification_test + consequence. Gemini nao oferece adversarial checking.

5. **Pipeline de $100**: nanochat-style — um dial (depth), minimo, zero external deps pesadas. Desktop com 8GB RAM + API keys = totalmente funcional.

### Onde Gemini Notebook e irreplicavel

1. **Produtividade de consumo**: Flashcards, podcasts, slides, infographics — formato de output que o usuario final quer consumir, nao executar.

2. **Network effects**: Sharing publico, featured notebooks, Spotify Wrapped integration — moats de distribuicao.

3. **Ecossistema Google**: Workspace sync, Drive auto-update, Sheets export — lock-in produtivo.

4. **Mobile-first**: 2 apps nativos vs. zero mobile no sop-extractor.

---

## 10. Recomendacoes Estrategicas

### Para o sop-extractor (proximas iteracoes)

| Prioridade | Item | Esforco | Impacto |
|---|---|---|---|
| **P0** | Fase 1: Teach Mode | 3 semanas | Habilita interacao LLM bidirecional |
| **P1** | Export SKILL.md -> .docx/.pdf | 1 semana | Output consumivel por nao-technical |
| **P1** | Web UI basica (Streamlit/gradio) | 2 semanas | Reduz barreira de entrada |
| **P2** | Audio overview (TTS do skill) | 1 semana | Compete com podcast do Gemini |
| **P2** | Mind map export (Mermaid/D3.js) | 1 semana | Visualizacao grafica |
| **P3** | Mobile PWA | 2 semanas | Acesso mobile |

### Posicionamento

> **sop-extractor nao compete com Gemini Notebook — eles servem momentos diferentes da mesma jornada de conhecimento.**
>
> Gemini Notebook = **consumo e compreensao** ("me ajuda a entender isso")
> sop-extractor = **compilacao e operacionalizacao** ("transforme isso em algo que um agent possa executar")
>
> O overlap existe na ingestao e sumarizacao, mas o output e fundamentalmente diferente: **resumo vs. skill acionavel**.
>
> Para o usuario que quer um podcast sobre seu documento -> Gemini Notebook.
> Para o usuario que quer uma skill executavel que captura a doutrina de um autor -> sop-extractor.

---

## Sources

- Wikipedia: Gemini Notebook (Jul 2026) — en.wikipedia.org/wiki/Gemini_Notebook
- Google Support: Create a notebook — support.google.com/gemininotebook/answer/16206563
- Google Support: Sources — support.google.com/gemininotebook/answer/16215270
- Google Support: Upgrade/Plans — support.google.com/gemininotebook/answer/16213268
- sop-extractor: scripts/menu.py (12 capabilities), explore agent inventory
- sop-extractor: MEMORY.md (architecture decisions, 5-point differentiation)
