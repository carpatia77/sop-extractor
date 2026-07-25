# Chavruta Engine — Debate Intensivo no /teach

> Plano de implementação do motor de debate interativo com tracking de profundidade.
> Fonte: `.mimocode/plans/sop-xtrata-1.md` §1713-§1912

---

## O que é Chavruta

**Chavruta** (חַבְרוּתָא) — aramaico para "parceria". Método tradicional de estudo judaico em dupla: dois estudiosos debatem um texto juntos, desafiando um ao outro.

> "Na diversidade de pensamento se produz mais conhecimento.
> Atinge-se a depth — como no xadrez, uma jogada de alta profundidade."

---

## Chavruta vs. LLM-as-a-Judge

| Aspecto | LLM-as-a-Judge | Chavruta |
|---------|----------------|----------|
| Quando atua | Depois (avalia resposta) | Durante (debate em tempo real) |
| O que faz | Nota, classifica | Desafia, pergunta, provoca |
| Relação | Juiz → réu | Parceiro → parceiro |
| Objetivo | Avaliar qualidade | Aprofundar compreensão |
| Output | Score + feedback | Perguntas + perspectivas |
| Depth | Não mede | Mede profundidade (1-7) |

---

## Semantic Field como substrato anti-hallucinação

**Insight crucial**: O Semantic Field é o **ground truth** que ancora o Chavruta.

```
SEM Semantic Field:
  LLM debate livre → alucina → drift → informação incorreta

COM Semantic Field:
  LLM debate ANCADO no graph → cada claim tem evidence_id
  → cada relação tem epistemic_status → não sai do escopo
```

O Semantic Field funciona como o **Talmud** para o Chavruta — o texto de referência que ambos os lados devem respeitar. Se o LLM tenta afirmar algo que não está no Semantic Field, o gate bloqueia.

```
FLUXO DE SEGURANÇA:
  Chavruta quer afirmar X
    → Busca X no Semantic Field
    → Encontrou com epistemic_status: certo? → OK, debate prossegue
    → Encontrou com epistemic_status: suposição? → "Isso é suposição, não fato"
    → Não encontrou? → "Isso não está na doutrina compilada"
```

---

## Níveis de profundidade (estilo xadrez)

```
Depth 1: SUPERFÍCIAL — "O que o autor diz sobre X?"
Depth 2: COMPREENSÃO — "Por que X em vez de Y?"
Depth 3: ANÁLISE — "O que acontece se X estiver errado?"
Depth 4: SÍNTESE — "Como X se conecta com Z?"
Depth 5: AVALIAÇÃO — "Você concorda? Por quê?"
Depth 6: CRIAÇÃO — "Como você aplicaria X diferente?"
Depth 7: META-COGNIÇÃO — "O que você não sabe que não sabe?"
```

### Analogia com xadrez

```python
ANALOGIES = {
    1: "Abertura — reconhece padrões básicos",
    2: "Desenvolvimento — entende o porquê",
    3: "Tática — calcula consequências",
    4: "Posicional — cruza ideias de múltiplos planos",
    5: "Estratégia — avalia trade-offs",
    6: "Criatividade — gera jogadas novas",
    7: "Maestria — compreende o que não sabe",
}
```

---

## Exemplo de debate (depth tracking)

```
USUÁRIO: "VRP negativo significa que não devemos vender prêmio."

CHAVRUTA [Depth 3]: 
"Espere. O autor disse 'não recomenda' venda cega, mas mencionou
short-gamma como alternativa em alguns ativos. Não é contradição?"

USUÁRIO: "Talvez short-gamma seja diferente de venda de prêmio."

CHAVRUTA [Depth 4]:
"Onde exatamente ele faz essa distinção? Mostre-me o trecho."

USUÁRIO: "Não lembro onde ele fala isso."

CHAVRUTA [Depth 5]:
"Isso é importante. Se você não consegue localizar, pode ser que:
1. O autor não fez essa distinção explicitamente
2. Está em outro vídeo não processado
3. Você está combinando dois conceitos separados
Qual hipótese é mais provável?"

USUÁRIO: "Provavelmente a 1 — eu estou inferindo."

CHAVRUTA [Depth 6]:
"Bom. Temos um candidato a 'suposição': 'short-gamma funciona
quando VRP é negativo' — mas o autor não afirma isso.
Vamos classificar como epistemic_status: suposição."

[Semantic Field atualizado com novo nó + edge]
```

---

## Arquitetura do Chavruta Engine

```
┌─────────────────────────────────────────────────────────────┐
│                    CHAVRUTA ENGINE                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  INPUT:                                                      │
│  ├── Usuário diz algo                                        │
│  ├── Semantic Field (ground truth)                           │
│  ├── Evidence Ledger (proveniência)                          │
│  ├── Refutation Chain (stress-test)                          │
│  ├── Depth atual                                             │
│  └── Histórico do debate                                     │
│                                                              │
│  PROCESSAMENTO:                                              │
│  1. Busca claim do usuário no Semantic Field                 │
│  2. Verifica epistemic_status                                │
│  3. Verifica evidence_ids                                    │
│  4. Verifica refutation chain (stress-test)                  │
│  5. Gera resposta desafiadora (baseada no SF)                │
│  6. Calcula nova depth                                       │
│  7. Atualiza Semantic Field (se novo insight)                │
│                                                              │
│  OUTPUT:                                                     │
│  ├── Pergunta desafiadora                                    │
│  ├── Referência ao Semantic Field                            │
│  ├── Refutation chain (se aplicável)                         │
│  ├── Depth atualizado                                        │
│  └── Novo nó/aresta no SF (se aplicável)                    │
│                                                              │
│  SEGURANÇA:                                                  │
│  ├── NÃO afirma algo que não está no SF                     │
│  ├── NÃO sai do escopo do task_contract                      │
│  ├── NÃO reconcilia contradições silenciosamente             │
│  ├── SEMPRE referencia evidence_id quando cita               │
│  └── USA refutation chain para stress-test                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Link com Refutation Chain

O Chavruta Engine é o **consumidor principal** do Refutation Chain durante o ensino interativo:

### Como o Refutation Chain alimenta o Chavruta

```
ANTES do Chavruta (compilação):
  compile.py → refutation_chain.py → strongest_alternative + disconfirming_evidence
  → salvo no Semantic Field como campos de principle nodes

DURANTE o Chavruta (ensino):
  Usuário afirma X
    → Chavruta busca X no SF
    → Encontra refutation chain de X
    → Usa strongest_alternative para desafiar o usuário
    → "Mas e se [strongest_alternative]? O autor considerou isso?"
    → Gate: refutation_disconfirming_evidence impede confirmação cega
```

### Integração específica

```python
class ChavrutaEngine:
    def generate_challenge(self, user_claim: str) -> str:
        # 1. Busca claim no Semantic Field
        node = self.sf.find_node(user_claim)
        
        # 2. Se tem refutation chain, usa para desafiar
        if node and node.get("strongest_alternative"):
            return self._challenge_with_refutation(
                user_claim,
                node["strongest_alternative"],
                node["disconfirming_evidence"],
                node["dissent_type"],
            )
        
        # 3. Senão, usa epistemic_status para desafiar
        if node and node.get("epistemic_status") == "speculative":
            return f"Isso é classificado como 'suposição' no SF. Qual é a evidência?"
        
        # 4. Senão, gera desafio baseado no SF
        return self._challenge_from_sf(user_claim)
    
    def _challenge_with_refutation(
        self, claim, alternative, disconfirming, dissent_type
    ) -> str:
        if dissent_type == "contradicts":
            return f"O SF tem um contraditor direto: {alternative}. Como você responde?"
        elif dissent_type == "qualifies":
            return f"O SF qualifica: {alternative}. Você considerou essa limitação?"
        else:  # context_limited
            return f"O SF diz que isso é verdade apenas em certos contextos: {alternative}. Qual contexto se aplica aqui?"
```

### Exemplo de integração

```
USUÁRIO: "Volatility drag sempre destrói valor."

CHAVRUTA (usando refutation chain):
"O SF tem uma refutation para esse claim:
- strongest_alternative: 'Volatility drag destrói valor geométrico, mas 
  rebalancing pode capturar volatilities harvesting premium'
- disconfirming_evidence: 'Seria falso se Sharpe ratio fosse path-independent'
- dissent_type: qualifies

O autor não diz que volatility drag SEMPRE destrói — ele diz que 
depende da abordagem. Você está simplificando?"
```

---

## Métrica de Depth

```python
class DepthTracker:
    """Rastreia profundidade do debate (estilo xadrez)."""
    
    def evaluate_move(self, user_response: str, semantic_field: dict) -> int:
        """Avalia profundidade. Semantic Field ancora a avaliação."""
        depth = 1
        # Depth 1: Repete o autor
        # Depth 2: Explica raciocínio
        # Depth 3: Aponta consequências
        # Depth 4: Cruza conceitos (verifica no Semantic Field)
        # Depth 5: Avalia e discorda (usa refutation chain)
        # Depth 6: Gera algo novo
        # Depth 7: Meta-cognição
        return depth
```

### Refutation Chain nos níveis de profundidade

| Depth | Nível | Uso do Refutation Chain |
|-------|-------|------------------------|
| 1 | Superficial | Não usa — repete o autor |
| 2 | Compreensão | Não usa — explica o porquê |
| 3 | Análise | Usa disconfirming_evidence — "O que acontece se for errado?" |
| 4 | Síntese | Usa strongest_alternative — "Como se conecta com outro conceito?" |
| 5 | Avaliação | Usa dissent_type — "Você concorda com a qualificação do SF?" |
| 6 | Criação | Usa refutation como catalisador — "Como você resolveria essa limitação?" |
| 7 | Meta-cognição | Usa refutation para mapear o que não se sabe |

---

## Integração com /teach mode

```bash
# Modo debate (depth tracking ativado)
sopx teach start caminho/para/fonte.pdf --mode chavruta

# Output:
# ═══════════════════════════════════════════════════════════
#   CHAVRUTA — Profundidade: 4/7 (Posicional)
#   "Cruza ideias de múltiplos planos"
#   Semantic Field: 47 nós, 32 arestas, 12 suposições
#   Refutation Chains: 15 principles, 8 qualifies, 3 contradicts
# ═══════════════════════════════════════════════════════════
#   
#   Chavruta: "Onde exatamente o autor faz essa distinção?"
#   
#   Você: [responde]
#   
#   Depth: 4 → 5 (Síntese → Avaliação)
#   ████░░░░░░░░░░░░ 57% profundidade
# ═══════════════════════════════════════════════════════════
```

---

## Por que Chavruta não alucina

```
SEM Semantic Field:
  LLM: "O autor disse que VRP sempre é negativo"  ← ALUCINAÇÃO
  (não tem referência, inventa)

COM Semantic Field:
  LLM busca "VRP" no SF → encontra: epistemic_status: provável
  LLM: "O autor classifica VRP como 'provável', não como 'certo'.
        Qual é a evidência? [ev-00142]"
  (ancorado no graph, não inventa)

SEM Evidence Ledger:
  LLM: "O autor disse X"  ← SEM PROVENIÊNCIA
  (não dá para verificar)

COM Evidence Ledger:
  LLM: "O autor disse X em [src2/2023-05-15, cap. 4, p. 87]"
  (rastreável, verificável)

SEM Refutation Chain:
  LLM: "O autor disse X"  ← SEM CONTRA-ARGUMENTO
  (aceita cedo demais)

COM Refutation Chain:
  LLM: "O autor disse X, mas o SF registra: [strongest_alternative].
        Como você responde a essa qualificação?"
  (stress-test, não confirmação cega)
```

---

## Módulos necessários

| Módulo | Status | Descrição |
|--------|--------|-----------|
| Semantic Field | ✅ Implementado | Ground truth para Chavruta |
| Evidence Ledger | ⚪ Parcial (campo evidence_id posicional; ledger real pendente) | Proveniência por claim |
| Refutation Chain | ✅ Implementado | Stress-test por claim |
| **Chavruta Engine** | ⚪ 0% | Motor de debate + depth tracking |
| **Depth Tracker** | ⚪ 0% | Métrica de profundidade (1-7) |
| **Drift Detector** | ⚪ 0% | Impede saída de escopo |
| **SF Validator** | ⚪ 0% | Ancora claims no Semantic Field |

---

## Estrutura de arquivos proposta

```
scripts/
├── chavruta/
│   ├── __init__.py
│   ├── engine.py          # ChavrutaEngine (motor principal)
│   ├── depth_tracker.py   # DepthTracker (métrica 1-7)
│   ├── drift_detector.py  # DriftDetector (anti-saída de escopo)
│   └── sf_validator.py    # SFValidator (ancora no Semantic Field)
└── teach/
    ├── __init__.py
    ├── session_manager.py # Gerencia 6 sessões
    ├── task_contract.py   # Sessão 1
    ├── evidence_ledger.py # Sessão 2
    ├── analysis.py        # Sessão 3 (coherence + evolution + refutation)
    ├── synthesis.py       # Sessão 4 (Semantic Field + emerging questions)
    ├── publication.py     # Sessão 5 (validators + publicação)
    └── application.py     # Sessão 6 (application_log + reflexão)
```

---

## Ordem de implementação sugerida

1. **Session Manager** (stateful, workspace)
2. **Task Contract** (Sessão 1)
3. **Evidence Ledger Integration** (Sessão 2)
4. **Analysis with Refutation** (Sessão 3)
5. **Synthesis** (Sessão 4)
6. **Publication** (Sessão 5)
7. **Application** (Sessão 6)
8. **Chavruta Engine** (motor de debate)
9. **Depth Tracker** (métrica)
10. **Drift Detector** (segurança)
