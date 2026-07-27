# Stress Test GURPS — Camada 4 vs Lexical (revisado)

## Setup

| Item | Valor |
|------|-------|
| SF | GURPS Basic Set — 23 nós |
| Modelo | all-MiniLM-L6-v2 (384 dims) |
| Queries | 14 (6 sinônimos, 2 exact, 3 paráfrases, 3 negativos) |
| Script | `tests/stress_test_camada4.py` (commitado, reproduzível) |
| Warmup | 5.6s (uma vez por processo) |

## Resultados corretos

| # | Query | Lexical | Emb Score | Emb Match | Correto? |
|---|-------|---------|-----------|-----------|----------|
| 1 | armor protection | damage-resistance-dr | 0.450 | damage-resistance-dr | ambos erram (ID esperado diferente) |
| 2 | dodge parry block | active-defense | 0.725 | active-defense | both OK |
| 3 | stamina fatigue | fatigue-points-fp | 0.551 | fatigue-points-fp | ambos erram (ID esperado diferente) |
| 4 | tech level civilization | tech-level-tl | 0.684 | tech-level-tl | ambos erram (ID esperado diferente) |
| 5 | **how hard to hit something** | **—** | 0.284 | **active-defense** | **emb only** |
| 6 | carrying capacity | encumbrance | 0.517 | encumbrance | both OK |
| 7 | Damage Resistance | damage-resistance-dr | 0.668 | principle:c0506e77 | **BOTH WRONG** (emb retorna nó errado) |
| 8 | Active Defense | active-defense | 0.638 | active-defense | both OK |
| 9 | how much punishment can I take | — | 0.358 | encumbrance | **BOTH WRONG** (deveria ser DR, não encumbrance) |
| 10 | movement penalty overencumbered | encumbrance | 0.625 | encumbrance | both OK |
| 11 | point buy character creation | character-creation | 0.410 | principle:b6b8cf59 | BOTH WRONG |
| 12 | cooking recipes | — | 0.161 | principle:a645e40b | lex only |
| 13 | stock market trading | — | 0.162 | principle:b6b8cf59 | lex only |
| 14 | python programming | — | 0.165 | sop:character-creation | lex only |

## Placar honesto (contagem simétrica)

| Métrica | Lexical | Embeddings |
|---------|---------|------------|
| Acerta sozinho | 3 (negativos corretamente rejeitados) | **1** ("how hard to hit") |
| Ambos acertam | 4 | 4 |
| Ambos erram | 6 | 6 |
| Total correto | 7/14 | 5/14 |

## Análise

### O que embeddings faz de único
- **"how hard to hit something"** → Active Defense (0.284) — paráfrase natural sem overlap lexical
- Única vitória exclusiva legítima

### O que embeddings erra
- **"how much punishment can I take"** → Encumbrance (0.358) — ERRADO. "Punishment" = dano, não carga. Deveria ser Damage Resistance.
- **"Damage Resistance"** → retorna principle:c0506e77 (nó errado, score 0.668) — falso positivo acima do threshold

### Threshold 0.50: zero contribuição efetiva
- 7 queries acima de 0.50 → todas já são capturadas pelo lexical
- Camada 4 só dispara quando Layers 1-3 retornam vazio
- Nenhuma das 7 queries acima do threshold ativa a Camada 4 em produção
- A única vitória exclusiva (0.284) está abaixo do threshold

### Margem de separação
- Positivos: 0.450–0.725
- Negativos: 0.161–0.165
- **Mas**: "Damage Resistance" (falso positivo) = 0.668 — acima de qualquer threshold razoável

## Parecer revisado

**Camada 4 está tecnicamente sólida** (código correto, 13 bugs fechados, fallback funcional).

**Mas neste teste não demonstra valor em produção**:
1. Ao threshold 0.50 (que evita FP), todas as queries acima já são cobertas pelo lexical
2. A única vitória exclusiva (0.284) está abaixo do threshold
3. Há 1 falso positivo real ("Damage Resistance" → nó errado, 0.668)

**Para capturar a vitória exclusiva**, threshold precisaria baixar para ~0.28 — mas a margem contra ruído encolhe (0.284 vs 0.165), e o FP em 0.668 mostra que o modelo erra em faixas altas.

**Recomendação**: Não declarar "pronta para produção" com base neste teste. A Camada 4 é uma ferramenta válida para quando o SF crescer (50+ nós) e as queries forem mais naturais — mas com 23 nós e queries que lexical já resolve, o custo-benefício não justifica a complexidade adicionada.

**Status correto**: Camada 4 implementada, testada, documentada — mas **não ativada por padrão**. Manter como opcional para uso futuro quando o corpus crescer.
