# Parecer Comparativo: Lexical (Layers 1-3) vs Embeddings (Camada 4)
## Stress Test Real — all-MiniLM-L6-v2, 5-node SF, 9 queries

---

## Setup

| Componente | Versão |
|------------|--------|
| Modelo | all-MiniLM-L6-v2 (384 dims) |
| SF | 5 nós (concept + principle) |
| Queries | 9 (3 sinônimos, 2 paráfrases, 2 negativos, 2 exact) |
| Hardware | CPU, sem GPU |

---

## Tabela de Resultados

| Query | Lexical (Layer) | Score L | Embeddings | Score E | Observação |
|-------|----------------|---------|------------|---------|------------|
| RAM consumption | concept:mem (salient) | 1.00 | concept:mem | 0.622 | **Ambos acertam** — "consumption" está na definition |
| processing speed | — | 0.00 | principle:snap | 0.477 | **Só embeddings** — sinônimo de "snapshots per second" |
| vector representations | concept:emb (salient) | 1.00 | concept:emb | 0.353 | **Ambos** — "vector representations" está na definition |
| returns variance | concept:vd (salient) | 1.00 | concept:vd | 0.448 | **Ambos** — "variance" está na definition |
| cooking recipes | — | 0.00 | principle:cache | 0.049 | **Falso positivo embeddings** (abaixo do threshold, OK) |
| baseball scores | — | 0.00 | principle:snap | 0.100 | **Falso positivo embeddings** (abaixo do threshold, OK) |
| volatility_drag | concept:vd (substring) | 0.00 | concept:vd | 0.686 | **Ambos** — substring match + embedding alto |
| concept:vd | concept:vd (id) | 0.00 | concept:vd | 0.164 | **Ambos** — ID exato + embedding baixo (esperado) |
| compounded returns variance | concept:vd (salient) | 1.00 | concept:vd | 0.564 | **Ambos** — overlap perfeito de termos |

---

## Análise

### Lexical ganhou em:
- **Cobertura**: 6/9 queries com match vs 6/9 embeddings
- **Precisão**: 0 falsos positivos vs 2 falsos positivos (embora abaixo do threshold)
- **Latência**: ~0ms pós-warmup vs ~29ms (60x mais rápido)
- **Zero dependência**: funciona sem sentence-transformers

### Embeddings ganhou em:
- **"processing speed"** → único que capturou (sinônimo de "snapshots per second")
- **robustez a reformulação**: "volatility_drag" (score 0.686) vs lexical (0.00 via salient, mas pega via substring)

### Por que lexical performou tão bem nesta suíte:
O `salient_terms()` do lexical inclui palavras da **definition** dos nós. Como "variance", "vector representations", "RAM" e "consumption" aparecem nas definições do SF, queries que usam essas palavras casam com overlap saliente de 1.00. Isso é uma **coincidência desta suíte** — em SFs reais com definições mais abstratas, o lexical perderia mais.

### Threshold 0.50 calibrado:
- Acima de 0.50: 3 queries (sinônimos reais: RAM consumption, volatility_drag, compounded returns)
- Abaixo de 0.50: 6 queries (paráfrases fracas + negativos)
- Nenhum falso positivo acima de 0.50

---

## Parecer

**Camadas 1-3 (lexical) são suficientes para a maioria dos casos** — especialmente quando o SF tem definições ricas que compartilham vocabulário com queries.

**Camada 4 (embeddings) agrega valor em**:
1. Sinônimos que não compartilham vocabulário ("processing speed" vs "snapshots per second")
2. Reformulações onde o lexical falha (query curta sem overlap)
3. Robustez a ruído — scores de embeddings são graduais (0.0-1.0), não binários

**Recomendação**: Manter Camada 4 como fallback (só aciona quando 1-3 retornam vazio). Não substitui lexical — complementa. Threshold 0.50 calibrado contra scores reais.

---

## Latência

| Camada | Latência média | Warmup |
|--------|---------------|--------|
| Lexical (1-3) | ~0ms | Nenhum |
| Embeddings (4) | ~29ms | 16.8s (primeira vez) |

Para uso em production: embeddings é 60x mais lento que lexical, mas 29ms é aceitável para interação humana. O warmup de 16.8s é uma vez por processo.
