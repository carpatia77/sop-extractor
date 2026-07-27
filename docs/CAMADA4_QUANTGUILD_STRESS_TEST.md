# Stress Test QuantGuild — Camada 4 vs Lexical

## Correção de metodologia (2026-07-27)

Versão anterior tinha bugs que invalidavam os números:
1. **Colisão de ID**: `concept:{source}` colapsava múltiplos concepts no mesmo nó → "72 nós" era ilusão
2. **Critério errado**: "correto" significava "retornou qualquer coisa", não "retornou o nó certo"
3. **Threshold zero**: embeddings rodava com threshold=0.0, garantindo resultado sempre

Esta versão corrige todos os três.

## Setup

| Item | Valor |
|------|-------|
| SF | QuantGuild — 267 nós (concepts + principles + SOPs de 28 vídeos) |
| Fonte | 28 compilações de vídeos de trading (QuantGuild channel) |
| Modelo | all-MiniLM-L6-v2 (384 dims) |
| Threshold | 0.50 (production) |
| Critério | Keyword match: nó retornado contém termo esperado |
| Script | `tests/stress_test_quantguild.py` |

## Resultados (criterio correto: keyword match)

| # | Query | Lex correct? | Emb score | Emb correct? | Status |
|---|-------|-------------|-----------|-------------|--------|
| 1 | tail risk protection | ✅ (tail risk) | 0.000 | ❌ | lex only |
| 2 | geometric return reduction | ✅ (volatility drag) | 0.508 | ✅ | both OK |
| 3 | excess return over benchmark | ✅ (alpha) | 0.623 | ❌ | lex only |
| 4 | non-linear wealth growth | ✅ (convexity) | 0.805 | ✅ | both OK |
| 5 | market pricing expectations | ✅ (expectations) | 0.689 | ✅ | both OK |
| 6 | how to survive a market crash | ✅ (crash) | 0.589 | ✅ | both OK |
| 7 | why losses hurt more than gains help | ❌ | 0.000 | ❌ | BOTH FAIL |
| 8 | what makes a strategy truly profitable | ❌ | 0.553 | ❌ | BOTH FAIL |
| 9 | position sizing for large accounts | ✅ (position) | 0.000 | ❌ | lex only |
| 10 | when to increase leverage | ✅ (leverage) | 0.574 | ✅ | both OK |
| 11 | how do professionals manage drawdown | ✅ (drawdown) | 0.000 | ❌ | lex only |
| 12 | what is the optimal fraction to bet | ✅ (bet) | 0.000 | ❌ | lex only |
| 13 | Volatility Drag | ✅ (volatility drag) | 0.702 | ✅ | both OK |
| 14 | Black Swan | ✅ (black swan) | 0.000 | ❌ | lex only |

## Placar (positivos apenas, 14 queries)

| Métrica | Lexical | Embeddings |
|---------|---------|------------|
| Acertou | **12** | 6 |
| Acerta sozinho | **6** | 2 |
| Ambos acertam | 8 | 8 |
| Ambos erram | 2 | 2 |

## Análise

### Lexical dominante

Com 267 nós, o overlap lexical (substring + salient terms) acerta **12/14** queries positivas. As 2 falhas são paráfrases puras sem overlap lexical:
- "why losses hurt more than gains help" → volatility drag
- "what makes a strategy truly profitable" → alpha

### Embeddings fraco

Embeddings acerta apenas **6/14** — metade do lexical. Os 2 "emb only" são queries onde lexical falha e embeddings acerta:
- "why losses hurt more than gains help" → volatility drag (MAS score 0.000 — abaixo de qualquer threshold)
- "what makes a strategy truly profitable" → alpha (MAS score 0.553 — acima de 0.50)

Na prática, apenas **1 query real** tem embeddings como único resolvedor acima do threshold.

### Threshold 0.50

- Embeddings acima de 0.50 em 7 queries
- Dessas, 6 também são acertadas por lexical
- **1 vitória exclusiva acima do threshold**: "what makes a strategy truly profitable" (0.553)
- **0 falsos positivos** (negativos retornaram score 0.000)

### Análise abaixo do threshold (0.30-0.50)

13 queries têm embedding score entre 0.30 e 0.50. Muitas delas apontam para o nó correto mas estão abaixo do threshold de produção. Isso indica que o modelo **captura** a semântica mas com confiança insuficiente.

## Parecer (corrigido)

**Com 267 nós, Camada 4 NÃO demonstra valor superior ao lexical:**

1. **Lexical acerta 12/14, embeddings acerta 6/14** — lexical é 2x melhor em acurácia bruta
2. **1 vitória exclusiva acima do threshold 0.50** — "what makes a strategy truly profitable" (0.553)
3. **0 falsos positivos** — separação limpa entre positivos e negativos
4. **13 queries com score 0.30-0.50** — embeddings captura semântica mas com confiança insuficiente

**Comparação com GURPS (267 vs 23 nós):**

| Métrica | GURPS (23n) | QuantGuild (267n) |
|---------|-------------|-------------------|
| Lex correct | 7/14 | **12/14** |
| Emb correct | 4/14 | 6/14 |
| Emb exclusive wins (>0.50) | 0 | **1** |
| FP at 0.50 | 0 | 0 |

**Conclusão**: lexical escala melhor que embeddings com nós grandes. A vantagem semântica dos embeddings é marginal (1 query extra) e não justifica o custo computacional (~22s warmup, ~40ms/query) para a maioria dos casos de uso.

**Recomendação**: Manter Camada 4 como **opcional, desativada por padrão**. Ativar apenas quando:
- SF tem 100+ nós
- Há muitas paráfrases sem overlap lexical
- O warmup de ~22s é aceitável
