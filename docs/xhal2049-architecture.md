# xHAL2049 — Diagrama de Arquitetura (Mermaid)

> O minerador de conhecimento humano — processa canais inteiros do YouTube e extrai o ouro.

## Visão Geral do Fluxo Completo

```mermaid
flowchart TB
    subgraph ENTRY["🎯 ENTRADAS (4 vias)"]
        direction LR
        A1["🔗 YouTube URL<br/>(1 vídeo)"]
        A2["📺 Canal/Playlist<br/>(N vídeos)"]
        A3["💾 Vídeo Local<br/>(MP4/MKV)"]
        A4["📄 PDF/EPUB/DOCX<br/>(texto)"]
    end

    subgraph M0["⚙️ MÓDULO 0: INGESTÃO"]
        B1["yt-dlp<br/>download"]
        B2["ffmpeg<br/>áudio + frames"]
        B3["faster-whisper<br/>transcrição → SRT"]
        B4["Cache Manager<br/>não reprocessa"]
        B5["Cost Estimator<br/>estima gastos"]
        B6["LLM Router<br/>motor certo/tarefa"]
    end

    subgraph M1["🔍 MÓDULO 1: ANÁLISE MULTIMODAL"]
        C1["Preflight Scan<br/>(texto)"]
        C2["VLM<br/>(análise visual)"]
        C3["NERRE<br/>(extração estruturada)"]
    end

    subgraph M2["📋 MÓDULO 2: EVIDENCE LEDGER"]
        D1["Proveniência<br/>por claim"]
        D2["Epistemic Status<br/>certo/provável/suposição"]
        D3["Refutation Chain<br/>strongest_alternative"]
        D4["Gates Determinísticos<br/>anti-hallucinação"]
    end

    subgraph M3["📚 MÓDULO 3: EXTRAÇÃO"]
        direction LR
        subgraph OLD["Existente"]
            E1["SKILL.md<br/>Steps 0-9"]
            E2["chapters/<br/>glossário"]
            E3["first_principles<br/>sops"]
        end
        subgraph NEWM["Novo"]
            E5["semantic_field/<br/>conceitos + relações"]
            E6["emerging_questions/<br/>lacunas"]
            E7["author_decisions.md<br/>ADRs do autor"]
            E8["concept_graph.graphml<br/>export graph"]
        end
    end

    subgraph M4["✅ MÓDULO 4: VALIDAÇÃO"]
        direction LR
        subgraph VOLD["7 scripts existentes"]
            F1["determinism_score"]
            F2["verify_concept_presence"]
            F3["validate_coherence"]
            F4["validate_evolution"]
            F5["validate_architecture"]
            F6["validate_manifest"]
            F7["validate_run_report"]
        end
        subgraph VNEW["3+ novos"]
            F8["validate_semantic_field"]
            F9["validate_evidence_ledger"]
            F10["F1 scoring<br/>automatizado"]
        end
    end

    subgraph M5["🔀 MÓDULO 5: CROSS-ANALYSIS"]
        G1["Consolida N vídeos<br/>em 1 graph"]
        G2["Detecta temas<br/>recorrentes"]
        G3["Rastreia evolução<br/>temporal"]
        G4["Extrai 'ouro'<br/>(conceitos raros)"]
        G5["Predição de links<br/>(node2vec)"]
    end

    subgraph M6["📊 MÓDULO 6: GRAPH + EXPORT"]
        H1["concept_graph.graphml"]
        H2["semantic_field.json<br/>(LightRAG/Cognee)"]
        H3["JSON-LD / GraphML export"]
    end

    subgraph M7["🎓 MÓDULO 7: ENSINO (Método Hebraico)"]
        I1["Sessão 1: Pergunta<br/>task_contract"]
        I2["Sessão 2: Contexto<br/>evidence_ledger"]
        I3["Sessão 3: Análise<br/>coherence + evolution"]
        I4["Sessão 4: Síntese<br/>semantic_field"]
        I5["Sessão 5: Conclusões<br/>publicação canônica"]
        I6["Sessão 6: Aplicação<br/>application_log"]
    end

    subgraph M8["⚔️ MÓDULO 8: CHAVRUTA ENGINE"]
        J1["Debate intensivo<br/>em tempo real"]
        J2["7 depths<br/>(xadrez analogy)"]
        J3["Semantic Field<br/>como ground truth"]
        J4["Anti-hallucinação<br/>por construção"]
    end

    subgraph OUT["📦 SAÍDA"]
        K1["Skill completa<br/>SKILL.md + chapters"]
        K2["Semantic Field<br/>JSON + MD"]
        K3["Concept Graph<br/>GraphML/JSON-LD"]
        K4["Emerging Questions"]
        K5["Relatório de Ouro"]
        K6["Ensinho Interativo<br/>(6 sessões)"]
        K7["Depth Report<br/>(profundidade)"]
    end

    %% Fluxo principal
    A1 & A2 & A3 & A4 --> B1
    B1 --> B2 --> B3
    B4 -.-> B3
    B5 -.-> C3
    B6 -.-> C3

    B3 --> C1
    B2 --> C2
    C1 & C2 & C3 --> D1
    D1 --> D2 --> D3 --> D4

    D4 --> E1 & E5
    E1 --> E2 & E3
    E5 --> E6 & E7 & E8

    E1 & E5 --> F1
    E8 --> F8
    F1 & F8 --> G1

    G1 --> G2 & G3 & G4 & G5
    G1 & G4 --> H1
    H1 --> H2 & H3

    H2 --> I1
    I1 --> I2 --> I3 --> I4 --> I5 --> I6

    I4 --> J1
    J1 --> J2
    J3 -.-> J1
    J4 -.-> J1

    I6 & J2 --> K1
    H2 --> K2 & K3
    G4 --> K5
    I6 --> K6
    J2 --> K7

    %% Estilos
    classDef entry fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    classDef module fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef old fill:#e8f5e9,stroke:#388e3c,stroke-width:1px
    classDef newn fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef output fill:#fce4ec,stroke:#c62828,stroke-width:2px

    class A1,A2,A3,A4 entry
    class B1,B2,B3,B4,B5,B6,C1,C2,C3,D1,D2,D3,D4,G1,G2,G3,G4,G5,H1,H2,H3,I1,I2,I3,I4,I5,I6,J1,J2,J3,J4 module
    class E1,E2,E3,F1,F2,F3,F4,F5,F6,F7 old
    class E5,E6,E7,E8,F8,F9,F10 newn
    class K1,K2,K3,K4,K5,K6,K7 output
```

---

## Fluxo de Decisão (LLM Router)

```mermaid
flowchart LR
    T["Tarefa"] --> R{"LLM Router"}

    R -->|"Extração<br/>(barato)"| L1["GPT-4o-mini<br/>$0.15/MTok"]
    R -->|"Classificação<br/>(barato)"| L2["Haiku 4.5<br/>$1/MTok"]
    R -->|"Análise visual<br/>(VLM)"| L3["GPT-4o<br/>$2.50/MTok"]
    R -->|"Síntese<br/>(premium)"| L4["Sonnet 5<br/>$2/MTok"]
    R -->|"Contradições<br/>(avançado)"| L5["Opus 4.8<br/>$5/MTok"]
    R -->|"Local<br/>(grátis)"| L6["Llama 3.3<br/>$0"]

    L1 & L2 & L3 & L4 & L5 & L6 --> O["Output"]

    classDef cheap fill:#e8f5e9,stroke:#388e3c
    classDef mid fill:#fff3e0,stroke:#f57c00
    classDef premium fill:#fce4ec,stroke:#c62828
    classDef local fill:#e3f2fd,stroke:#1565c0

    class L1,L2 cheap
    class L3,L4 mid
    class L5 premium
    class L6 local
```

---

## Fluxo Chavruta (Debate + Depth)

```mermaid
flowchart TB
    U["Usuário diz algo"] --> SF{"Semantic Field<br/>(ground truth)"}

    SF -->|"Encontrou<br/>epistemic: certo"| OK["OK — debate prossegue"]
    SF -->|"Encontrou<br/>epistemic: suposição"| WARN["⚠ 'Isso é suposição,<br/>não fato'"]
    SF -->|"Não encontrou"| BLOCK["🚫 'Isso não está<br/>na doutrina compilada'"]

    OK --> CH["Chavruta gera<br/>pergunta desafiadora"]
    WARN --> CH
    BLOCK --> CH

    CH --> D{"Depth atual?"}

    D -->|"1-2"| D12["Abertura/Desenvolvimento<br/>reconhece padrões"]
    D -->|"3-4"| D34["Tática/Posicional<br/>cruza conceitos"]
    D -->|"5-6"| D56["Estratégia/Criatividade<br/>avalia e gera novos"]
    D -->|"7"| D7["Maestria<br/>meta-cognição"]

    D12 & D34 & D56 & D7 --> U

    classDef sf fill:#e8f5e9,stroke:#388e3c
    classDef ok fill:#e3f2fd,stroke:#1565c0
    classDef warn fill:#fff3e0,stroke:#f57c00
    classDef block fill:#fce4ec,stroke:#c62828
    classDef depth fill:#f3e5f5,stroke:#7b1fa2

    class SF sf
    class OK ok
    class WARN warn
    class BLOCK block
    class D12,D34,D56,D7 depth
```

---

## Fluxo de Ingestão Massiva (Canal)

```mermaid
flowchart LR
    subgraph INPUT["Entrada"]
        URL["youtube.com/@canal"]
    end

    subgraph PHASE1["Fase 1: Descoberta"]
        Y1["yt-dlp lista<br/>todos os vídeos"]
        Y2["Filtra: só<br/>educativos"]
        Y3["Ordena<br/>cronologicamente"]
    end

    subgraph PHASE2["Fase 2: Processamento"]
        P1["Paralelo: N vídeos"]
        P2["Download + SRT"]
        P3["Frames + VLM"]
        P4["Extração conceitos"]
    end

    subgraph PHASE3["Fase 3: Cross-Analysis"]
        X1["Consolida conceitos"]
        X2["Detecta temas"]
        X3["Rastreia evolução"]
        X4["Extrai ouro"]
    end

    subgraph PHASE4["Fase 4: Output"]
        O1["Concept Graph"]
        O2["Semantic Field"]
        O3["Skill consolidada"]
        O4["Relatório de ouro"]
    end

    URL --> Y1 --> Y2 --> Y3
    Y3 --> P1
    P1 --> P2 & P3 & P4
    P2 & P3 & P4 --> X1
    X1 --> X2 & X3 & X4
    X2 & X3 & X4 --> O1 & O2 & O3 & O4
```

---

## Comparação: ATUAL vs. xHAL2049

```mermaid
flowchart LR
    subgraph NOW["v2.1.1 (ATUAL)"]
        N1["PDF/EPUB/SRT/TXT"]
        N2["Pre-flight Scan"]
        N3["LLM Extrai"]
        N4["7 Validators"]
        N5["Skill Output"]
    end

    subgraph FUTURE["v3.0 (xHAL2049)"]
        F1["+ YouTube/Canal/Vídeo"]
        F2["+ VLM + NERRE"]
        F3["+ Evidence Ledger"]
        F4["+ Semantic Field"]
        F5["+ Concept Graph"]
        F6["+ 6 Sessões Judaicas"]
        F7["+ Chavruta (7 depths)"]
        F8["+ Gold Extraction"]
    end

    N1 --> N2 --> N3 --> N4 --> N5

    N1 -.-> F1
    N2 -.-> F2
    N3 -.-> F3
    N4 -.-> F4
    N5 -.-> F5
    F5 --> F6 --> F7
    F5 --> F8

    classDef now fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    classDef future fill:#fff3e0,stroke:#f57c00,stroke-width:2px

    class N1,N2,N3,N4,N5 now
    class F1,F2,F3,F4,F5,F6,F7,F8 future
```

---

## Para usar

1. Copie para `docs/xhal2049-architecture.md`
2. **GitHub/GitLab**: visualiza automaticamente
3. **Mermaid Live**: cole em [mermaid.live](https://mermaid.live)
4. **VS Code**: extensão "Mermaid Preview"
5. **CLI**: `mmdc -i xhal2049-architecture.md -o xhal2049-architecture.png`
