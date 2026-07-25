# Auditor Fixes — Pre-Implementation Corrections

## Contexto

O engenheiro auditor revisou `TEACH_MODE_PLAN.md` e `CHAVRUTA_ENGINE_PLAN.md` e identificou 4 issues que precisam ser resolvidos ANTES de implementar código. Este plano documenta o que cada issue exige e a ordem de execução.

---

## Issue 1: 🔴 DepthTracker — hand-wave (CRÍTICO)

**Problema**: `evaluate_move()` é um stub com `return depth`. Classificar fala do usuário em taxonomia Bloom de 7 níveis via LLM herda subjetividade — exatamente o que o projeto elimina nos outros gates.

**Solução**: Depth = função de **eventos observáveis no grafo**, não nota subjetiva.

### Mecanismo proposto

```python
def evaluate_move(user_response: str, sf: dict, refutation: dict | None,
                  task_contract: dict = None) -> int:
    """Depth derivada de quais artefatos do SF o movimento toca.
    Regra: depth = max(disparados). Ordem das checagens nao afeta resultado."""
    scores = []

    # Depth 1: Repete o autor (nao adiciona nada)
    # → detectar: resposta contém apenas terms ja presentes no SF sem cruzamento

    # Depth 2: Explica raciocínio
    # → detectar: resposta referencia um node com evidence_id

    # Depth 3: Aponta consequências (usa disconfirming_evidence)
    # → detectar: resposta invoca conceito ligado a um refutation

    # Depth 4: Cruza conceitos (dois nós conectados)
    # → detectar: resposta menciona dois nodes que share uma aresta used_in

    # Depth 5: Avalia/discorda (usa strongest_alternative)
    # → detectar: resposta invoca um strongest_alternative do SF

    # Depth 6: Gera algo novo (termo novo ancorado — NAO e drift)
    # → detectar: resposta contém termo nao mapeado MAS ancorado em:
    #   - strongest_alternative existente, OU
    #   - user_goal do task_contract, OU
    #   - evidencia de um node
    # → Se sem ancora = drift (DriftDetector, nao Depth 6)

    # Depth 7: Meta-cognição
    # → detectar: resposta contém markers de uncertainty ("nao sei", "nao tenho certeza",
    #             "isso e suposição") E referencia SF

    return max(scores) if scores else 1
```

### Critérios observáveis (grounded, testável)

| Depth | Critério observável | Fonte de dados |
|-------|-------------------|----------------|
| 1 | Resposta repete termos SF sem cruzamento | term frequency no SF |
| 2 | Resposta referencia 1 node com evidence_id | SF node lookup |
| 3 | Resposta invoca disconfirming_evidence | refutation chain |
| 4 | Resposta menciona 2+ nodes conectados por aresta | SF edge traversal |
| 5 | Resposta invoca strongest_alternative | refutation chain |
| 6 | Resposta contém termo novo **ancorado** num node existente via aresta proposta | SF + task_contract |
| 7 | Resposta tem uncertainty markers + referência SF | regex + SF lookup |

### Regra de monotonicidade

`depth = max(disparados)`. Uma fala pode disparar múltiplos critérios (ex: menciona 2 nós conectados **e** invoca strongest_alternative → depth = max(4, 5) = 5). Ordem das checagens no código não afeta o resultado.

### Desempate Depth 6 vs Drift Detector

**Mesmo sinal observável** ("termo não mapeado no SF"), **significados opostos**:
- Depth 6 (criação): termo novo **ancorado** — o usuário propõe algo que se conecta a um node existente
- Drift: termo novo **sem âncora** — o usuário fala de algo completamente fora do SF

**Regra de desempate**:
```python
def _is_creation_vs_drift(new_term: str, sf: dict, task_contract: dict) -> str:
    """Desempata entre criacao (depth 6) e drift."""
    # 1. O termo novo aparece em strongest_alternative de algum principle?
    for node in sf.get("nodes", []):
        alt = node.get("strongest_alternative", "")
        if new_term.lower() in alt.lower():
            return "creation"  # ancorado em refutation chain

    # 2. O termo novo está alinhado com user_goal do task_contract?
    user_goal = task_contract.get("user_goal", "").lower()
    if any(w in user_goal for w in new_term.lower().split()):
        return "creation"  # ancorado no objetivo do usuário

    # 3. O termo novo aparece na evidência de algum node?
    for node in sf.get("nodes", []):
        evidence = node.get("evidence", "")
        if new_term.lower() in evidence.lower():
            return "creation"  # ancorado na evidência

    # 4. Sem âncora = drift
    return "drift"
```

### Arquivos a criar/modificar

- `scripts/chavruta/depth_tracker.py` — implementação grounded com `max()` rule
- `tests/test_depth_tracker.py` — testes com fixtures de SF mockado

---

## Issue 2: 🟠 Evidence Ledger — marcado como pronto, não existe

**Problema**: Tabela Pareto marca "Evidence Ledger ✅ 100%" mas:
- Não existe `scripts/evidence_ledger.py`
- `evidence_id` em principle nodes = `f"{source_file}#principle:{len(principle_nodes)}"` (posicional, não âncora real)
- `evidence_id` em concept/reference nodes = `None`
- O `evidence_ledger.json` é listado como **output a ser criado** na Sessão 2

**Solução honesta**: Criar o Evidence Ledger como módulo real, ou rebaixar o status para refletir a realidade.

### O que o Evidence Ledger DEVE ser

```json
{
  "entries": [
    {
      "entry_id": "ev-abc123",
      "claim": "Volatility drag compounds against you",
      "source_file": "video_abc/transcript.srt",
      "source_sha256": "abc...",
      "upload_date": "2024-05-15",
      "locator": "00:12:34-00:13:02",
      "excerpt_hash": "def...",
      "epistemic_status": "certain",
      "evidence_text": "Author states at 12:34 that volatility drag compounds",
      "refutation": {
        "strongest_alternative": "...",
        "disconfirming_evidence": "...",
        "dissent_type": "qualifies"
      }
    }
  ],
  "metadata": {
    "source_count": 1,
    "total_entries": 5,
    "built_at": "2026-07-25T10:00:00Z"
  }
}
```

### O que existe hoje vs o que falta

| Campo | Status | O que falta |
|-------|--------|------------|
| `entry_id` | ❌ Não existe | Gerar UUID determinístico |
| `claim` | ✅ Existe (principle.statement) | — |
| `source_file` | ✅ Existe (source_path) | — |
| `source_sha256` | ✅ Existe | — |
| `upload_date` | ✅ Existe (metadata.json) | — |
| `locator` | ❌ Não existe | Timestamp SRT ou page number |
| `excerpt_hash` | ❌ Não existe | Hash do trecho original |
| `epistemic_status` | ✅ Existe | — |
| `evidence_text` | ❌ Não existe | Trecho literal da fonte |
| `refutation` | ✅ Existe (refutation_chain.py) | — |

### Arquivos a criar

- `scripts/evidence_ledger.py` — módulo de ledger
- `tests/test_evidence_ledger.py` — testes
- Atualizar `semantic_field.py` para usar `entry_id` real em vez de posicional

### Prioridade

**Média** — o refutation chain já funciona. O Evidence Ledger real é necessário para Sessão 2 do Teach Mode, mas não bloqueia o Chavruta mínimo (que pode usar o SF atual).

---

## Issue 3: 🟠 find_node / Drift Detector — trabalho escondido

**Problema**: "Busca X no Semantic Field" esconde matching fuzzy de linguagem natural contra nós do grafo. Sem mecanismo concreto, o gate "não afirma o que não está no SF" não é confiável.

**Solucao**: Abordagem de 3 camadas

### Camada 1: Match exato por ID
```python
node = sf.get_node_by_id(query)  # busca por "principle:abc123"
```

### Camada 2: Match por substring em statement/term
```python
for node in sf.nodes:
    if query.lower() in node.get("statement", "").lower():
        matches.append(node)
    if query.lower() in node.get("term", "").lower():
        matches.append(node)
```

### Camada 3: Match por salient terms (reutilizar verify_concept_presence)
```python
from verify_concept_presence import salient_terms
query_terms = set(salient_terms(query))
for node in sf.nodes:
    text = node.get("statement", "") or node.get("definition", "")
    node_terms = set(salient_terms(text))
    overlap = len(query_terms & node_terms) / len(query_terms | node_terms)
    if overlap > 0.3:
        matches.append((node, overlap))
```

### Drift Detector
```python
def detect_drift(user_response: str, sf: dict, task_contract: dict) -> bool:
    """Retorna True se resposta está fora do escopo."""
    # 1. Verificar se termos da resposta existem no SF
    # 2. Verificar se termos estão alinhados com user_goal do task_contract
    # 3. Se <20% dos termos mapeiam para SF → drift provável
```

### Arquivos a criar

- `scripts/chavruta/sf_matcher.py` — matching multi-camada
- `scripts/chavruta/drift_detector.py` — detecção de drift
- `tests/test_sf_matcher.py`
- `tests/test_drift_detector.py`

---

## Issue 4: 🟡 Ausência de estratégia de eval

**Problema**: Zero estratégia de teste/eval para Chavruta. Para um projeto cuja tese é anti-fabricação, embarcar um debatedor sem harness de eval é fora da marca.

**Solução**: Definir eval harness ANTES de implementar.

### Eval categories

| Categoria | O que testa | Como testa |
|-----------|------------|-----------|
| **Anti-hallucination** | Chavruta nao afirma algo fora do SF | Fixture: claim nao esta no SF -> deve bloquear |
| **Depth accuracy** | Depth score é grounded | Fixture: resposta com 2 nós conectados → depth ≥ 4 |
| **Drift detection** | Sai do escopo → detecta | Fixture: resposta sobre tema não mapeado → drift=True |
| **Refutation integration** | Usa strongest_alternative | Fixture: principle com refutation → Chavruta o invoca |
| **No silent reconciliation** | Contradições não são ignoradas | Fixture: claim contradiz SF → Chavruta aponta |

### Arquivos a criar

- `tests/test_chavruta_eval.py` — eval harness
- `tests/fixtures/chavruta/` — fixtures de SF mockado + responses

### Prioridade

**Alta** — deve ser criado ANTES do código do Chavruta, não depois.

---

## Ordem de Execução (Revisada)

### Fase A: Corrigir planos (hoje)
1. ✅ Auditor review concluído
2. Atualizar `CHAVRUTA_ENGINE_PLAN.md` com depth grounded
3. Atualizar `TEACH_MODE_PLAN.md` com status honesto do Evidence Ledger
4. Criar `docs/CHAVRUTA_EVAL_PLAN.md` com eval harness

### Fase B: Foundation (antes de Chavruta)
1. `scripts/chavruta/sf_matcher.py` — matching multi-camada
2. `scripts/chavruta/drift_detector.py` — detecção de drift
3. `tests/test_sf_matcher.py` + `tests/test_drift_detector.py`
4. `tests/test_chavruta_eval.py` — eval harness

### Fase C: Depth Tracker (core do produto)
1. `scripts/chavruta/depth_tracker.py` — implementação grounded
2. `tests/test_depth_tracker.py` — testes com fixtures

### Fase D: Evidence Ledger (honestidade)
1. `scripts/evidence_ledger.py` — módulo de ledger
2. Atualizar `semantic_field.py` para usar entry_id real
3. `tests/test_evidence_ledger.py`

### Fase E: Chavruta Engine (motor)
1. `scripts/chavruta/engine.py` — motor principal
2. `tests/test_chavruta_engine.py`

### Fase F: Teach Mode (6 sessões)
1. `scripts/teach/session_manager.py`
2. Sessões 1-6
3. `tests/test_teach_*.py`

---

## Resumo: O que o auditor pediu vs o que vamos fazer

| Auditor pediu | Ação | Prioridade |
|---------------|------|-----------|
| Depth grounded em eventos do grafo | `depth_tracker.py` com critérios observáveis | 🔴 CRÍTICO |
| Evidence Ledger honesto | Criar módulo ou rebaixar status | 🟠 ALTA |
| find_node concreto | `sf_matcher.py` multi-camada | 🟠 ALTA |
| Eval harness | `test_chavruta_eval.py` antes do código | 🟡 MÉDIA |
| Vertical slice primeiro | Sessão 1 + Chavruta mínimo antes das 6 sessões | 🟡 MÉDIA |
| Tabelas comparativas sao marketing | Remover ou contextualizar | 🟢 Baixa |
