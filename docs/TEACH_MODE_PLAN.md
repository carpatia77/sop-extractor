# Teach Mode — 6 Sessões (Método Judaico)

> Plano de implementação do ensino interativo multi-sessão com workspace stateful.
> Fonte: `.mimocode/plans/sop-xtrata-1.md` §450-§825

---

## Visão Geral

**Base filosófica**: Método Judaico de Estudo — "Aprender não é luxo, é um dever e uma disciplina contínua. Sabedoria que não vira vida, para no papel."

**Comandos CLI**:
```bash
sopx teach start caminho/para/fonte.pdf              # Sessão 1
sopx teach continue caminho/para/skill-dir            # Qualquer sessão
sopx teach status caminho/para/skill-dir              # Ver progresso
sopx teach session caminho/para/skill-dir --session 3 # Retomar sessão específica
sopx teach close caminho/para/skill-dir               # Sessão 6 (encerramento)
```

---

## Fluxo Completo

```
                    ┌──────────────────┐
                    │  Pergunta inicial │  ← Sessão 1 (judaico)
                    │  task_contract    │     /grill-me (Pocock)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Leitura +       │  ← Sessão 2 (judaico)
                    │  Contexto        │     CONTEXT.md (Pocock)
                    │  evidence_ledger │     pre-flight (sop-extractor)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Análise e       │  ← Sessão 3 (judaico)
                    │  Comparação      │     /domain-modeling (Pocock)
                    │  coherence +     │     4 temporal gates
                    │  evolution audit │     (sop-extractor)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Síntese         │  ← Sessão 4 (judaico)
                    │  Semantic Field  │     /grill-with-docs (Pocock)
                    │  + epistemic     │     Semantic Field
                    │  status          │     (sop-extractor)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Conclusões      │  ← Sessão 5 (judaico)
                    │  Publicação      │     /to-spec (Pocock)
                    │  canônica        │     validators (sop-extractor)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  APLICAÇÃO       │  ← Sessão 6 (judaico)
                    │  Reflexão        │     /teach stateful (Pocock)
                    │  Próximo passo   │     "Agency > Intel" (Karpathy)
                    │  application_log │     NENHUM OUTRO TEM ISTO
                    └──────────────────┘
```

---

## Sessão 1: PERGUNTA (Passo 1 — Ative o cérebro)

**Input**: obra do autor (PDF, curso, transcrição)
**Ação**: Entrevista o usuário ANTES de compilar

**Perguntas**:
- "O que você quer entender nesta obra?"
- "Qual problema você tenta resolver?"
- "Você quer fundamentos ou procedimentos?"
- "Tem fontes complementares para cruzar?"

**Output**: `task_contract.json`
```json
{
  "user_goal": "string",
  "intended_outcome": "string",
  "interpretation": "string",
  "ambiguity_status": "resolved|partial|unresolved"
}
```

**Gate**: Nenhuma compilação começa sem pergunta clara

**Referência judaica**: "Uma pergunta boa abre um estudo bom."
**Referência Pocock**: /grill-me (entrevista antes de agir)

### Adaptação de Pocock

Pocock faz:
```
One question at a time. Look up facts, ask for decisions.
Don't act until confirmed.
```

sop-xtrata adapta:
```
1. Pre-flight scan descobre fatos (formato, tamanho, tipo)
2. Uma pergunta por vez ao usuário
3. Usuário confirma → task_contract.json é gravado
4. Nenhuma compilação começa sem task_contract válido
```

---

## Sessão 2: LEITURA ATENTA + CONTEXTO (Passos 2-3)

**Input**: fonte do autor + task_contract
**Ação**: Pre-flight scan + extração determinística

**Perguntas contextuais (gate obrigatório)**:
- "Quem é o autor? Qual sua autoridade?"
- "Para quem foi escrito?"
- "Em que momento histórico?"
- "Qual o propósito do autor?"

**Output**: `evidence_ledger.json`
```json
{
  "source_id": "string",
  "source_date": "YYYY-MM-DD",
  "locator": "string",
  "excerpt_hash": "string"
}
```

**Gate**: Nenhum claim sem evidence_id válido

**Referência judaica**: "Nenhuma palavra é neutra." / "Texto sem contexto gera leitura rasa."
**Referência Pocock**: CONTEXT.md + ADRs

---

## Sessão 3: ANÁLISE E COMPARAÇÃO (Passo 4 — A verdade se afia)

**Input**: evidence_ledger + múltiplas fontes (se disponíveis)
**Ação**: Coherence audit + Evolution audit

**Perguntas**:
- "O autor contradiz a si mesmo?"
- "Onde a doutrina mudou ao longo do tempo?"
- "Há tensões não resolvidas?"
- "O que outra fonte diz sobre o mesmo tema?"

**Output**: `coherence_audit.md` + evolution audit
(contradictions flagged, tensions opened)

**Gate**: Contradições não são reconciliadas silenciosamente

**Referência judaica**: "Comparar não confunde, aprofunda."
**Referência Pocock**: /domain-modeling (stress-test com edge cases)
**Referência sop-extractor**: 4 temporal gates (já existentes)

### Link com Refutation Chain

A Sessão 3 é onde o **Refutation Chain** (`scripts/refutation_chain.py`) se encaixa naturalmente:

```
Sessão 3: ANÁLISE E COMPARAÇÃO
├── Coherence audit (já existe: validate_coherence_audit.py)
├── Evolution audit (já existe: validate_evolution_audit.py)
└── Refutation Chain (NOVO: refutation_chain.py)
    ├── Para cada principle: strongest_alternative
    ├── Para cada principle: disconfirming_evidence
    └── Validação: alternativa genuinamente OPÕE o claim
```

O Refutation Chain adiciona a camada de "stress-test" que faltava:
- Coherence audit detecta contradições ENTRE capítulos/fontes
- Evolution audit detecta mudanças TEMPORAIS na doutrina
- **Refutation Chain testa cada claim individualmente** — "como derrubar essa afirmação?"

---

## Sessão 4: SÍNTESE — VOCÊ PROCESSA (Passo 5 — Não é esponja)

**Input**: evidence_ledger + audits + task_contract
**Ação**: Gerar Semantic Field + Emerging Questions

**Processo**:
1. LLM propõe nós (conceitos, métricas, mecanismos)
2. LLM propõe arestas (relações do vocabulário fechado)
3. Cada item classificado: certo / provável / suposição / não_sei
4. Auto-ataque para claims causais e quantitativos
5. Perguntas emergentes apenas de lacuna, tensão ou limite

**Output**:
- `semantic_field.candidates.jsonl`
- `emerging_questions.candidates.jsonl`

**Gate**: Nada publicado sem epistemic_status + evidence_ids

**Referência judaica**: "Você não é uma esponja; é um processador."
**Referência Pocock**: /grill-with-docs (domain model + CONTEXT.md)

### Link com Semantic Field + Refutation Chain

A Sessão 4 consolida tudo no Semantic Field:

```
Sessão 4: SÍNTESE
├── Input: evidence_ledger (Sessão 2) + audits (Sessão 3) + refutation chains
├── Processo: LLM propõe nós + arestas
├── Gate: epistemic_status obrigatório
├── Gate: evidence_id obrigatório
└── Output: semantic_field.candidates.jsonl
```

O Semantic Field agora carrega os dados do Refutation Chain:
```json
{
  "type": "principle",
  "statement": "VRP negativo indica oversold",
  "epistemic_status": "probable",
  "evidence_id": "video_abc#principle:3",
  "strongest_alternative": "VRP negativo pode indicar apenas baixa demanda por hedge",
  "disconfirming_evidence": "Seria falso se VRP fosse apenas medida de demanda",
  "dissent_type": "qualifies"
}
```

---

## Sessão 5: CONCLUSÕES PRÓPRIAS (Passo 5 continued)

**Input**: candidatos da sessão 4
**Ação**: Revisão + publicação canônica

**Processo**:
1. Usuário revisa candidatos por status
2. Aprova, rejeita, reduz escopo, marca como não_sei
3. Validators executam todos os gates
4. Publica `semantic_field.json` + `semantic_field.md`
5. Publica `emerging_questions.md`

**Output**: artefatos canônicos (só itens aprovados)

**Gate**: nenhum proposed/rejected aparece no canônico

**Referência judaica**: "Escreva com suas próprias palavras. Crie conexões. Estruture e tire conclusões."
**Referência Pocock**: /to-spec (transforma em spec publicada)

---

## Sessão 6: APLICAÇÃO — O FECHAMENTO DO CICLO (Passo 6)

**Input**: artefatos canônicos + sessões anteriores
**Ação**: Estado de aplicação + reflexão

**Perguntas**:
- "Como isso muda sua prática?"
- "Qual é o próximo passo concreto?"
- "O que você vai aplicar hoje?"
- "O que ainda não entendeu?"

**Output**: `application_log.json`
```json
{
  "session_id": "string",
  "applied_actions": ["string"],
  "open_questions": ["string"],
  "next_step": "string",
  "reflection": "string"
}
```

**Stateful**: cada sessão futura consulta o application_log para evitar repetir e Progressivo

**Referência judaica**: "Sabedoria que não vira vida, para no papel." / "Discuta, ensine e aplique." / "Sempre pergunte: o que posso fazer com o que aprendi hoje?"
**Referência Pocock**: /teach (workspace stateful)
**Referência Karpathy**: "Agency > Intelligence"

---

## Arquivos do Teach Mode

```
<skill-dir>/
├── teach/
│   ├── task_contract.json          # Sessão 1: pergunta + objetivo
│   ├── context_questions.json      # Sessão 2: quem, para quem, quando
│   ├── session_log.jsonl           # Log de todas as sessões
│   ├── application_log.json        # Sessão 6: aplicação + reflexão
│   └── progress.json               # Estado stateful entre sessões
├── evidence/
│   └── evidence_ledger.json        # Sessão 2: proveniência
├── semantic_field/
│   ├── semantic_field.candidates.jsonl  # Sessão 4: candidatos
│   ├── semantic_field.json             # Sessão 5: publicado
│   └── semantic_field.review.json      # Sessão 5: decisões
├── emerging_questions/
│   ├── emerging_questions.candidates.jsonl
│   └── emerging_questions.md
├── assurance/
│   ├── run_manifest.json
│   └── decision_log.json
└── SKILL.md
```

---

## Zona de Desenvolvimento Proximal (ZPD)

```python
def calibrate_depth(skill_dir: str, progress: dict) -> int:
    """Calibra a profundidade da próxima sessão baseado no progresso."""
    # Sessão não completada → retomar de onde parou
    # Sessão completada → avançar para próxima
    # Usuário avançado → pular para sessão mais avançada
```

---

## O que NINGUÉM mais terá

| Capacidade | sop-xtrata | Pocock | LightRAG | Cognee |
|------------|-----------|--------|----------|--------|
| Método Judaico completo (6 passos) | **SIM** | - | - | - |
| Compilar doutrina + ensinar | **SIM** | parcial | - | - |
| Epistemic status + gates | **SIM** | - | - | - |
| Provenance → Refutation | **SIM** | - | - | - |
| Domain model + teaching | **SIM** | parcial | - | - |
| Stateful multi-sessão | **SIM** | **SIM** | - | - |
| Aplicação + reflexão (Passo 6) | **SIM** | - | - | - |
| Graph RAG ready | **SIM** | - | **SIM** | **SIM** |

---

## Dependências para Implementação

| Componente | Status | Dependências |
|------------|--------|-------------|
| Ingestão (yt-dlp + whisper) | ✅ 100% | Nenhuma |
| Evidence Ledger | ✅ Implementado (entry_id + locator + excerpt_hash + evidence_text) | Ingestão |
| Semantic Field | ✅ 100% | Evidence Ledger |
| Cross-Analysis | ✅ 100% | Semantic Field |
| **Teach Mode (6 sessões)** | ⚪ 0% | Evidence Ledger + Semantic Field |
| **Chavruta Engine** | ⚪ 0% | Semantic Field + Teach Mode |
