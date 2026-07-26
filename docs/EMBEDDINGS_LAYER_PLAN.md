# Embeddings Layer (Camada 4) — sf_matcher.py

## Status: PLANEJADO (não implementado)

## Problema

O matching keyword-based (Jaccard/salient terms) não captura similaridade semântica real:

| Query | Resultado atual | Com embeddings |
|-------|----------------|----------------|
| "sword" | NENHUM | → "weapon" (similaridade semântica) |
| "psionics" | NENHUM | → conceitos relacionados |
| "Can I use magic and psionics together?" | NENHUM | → matching composto |
| "memory usage" vs "RAM consumption" | NENHUM | → sinônimos |

## Solução: Camada 4 opcional

Adicionar embedding-based matching como Camada 4 no `sf_matcher.py`, sem mudar as camadas existentes.

### Implementação

1. **Pré-computar embeddings** de cada nó do SF (statement + term + definition)
2. **Embedding do query** no runtime
3. **Cosine similarity** como score
4. **Threshold configurável** (default 0.7)

### Dependências

| Opção | Modelo | Custo | Latência |
|-------|--------|-------|----------|
| sentence-transformers (local) | all-MiniLM-L6-v2 | 0 (RAM ~80MB) | ~10ms/query |
| OpenAI API | text-embedding-3-small | ~$0.0001/query | ~100ms |
| Google API | text-embedding-004 | ~$0.0001/query | ~100ms |

### Código (esqueleto)

```python
# Camada 4: Embeddings (opcional)
def match_by_embedding(query: str, sf: dict, threshold: float = 0.7) -> list[tuple[dict, float]]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return []  # Fallback: sem embeddings, retorna vazio
    
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Embeddings pré-computados do SF (cacheados)
    if not hasattr(sf, '_embeddings'):
        texts = [n.get('statement', '') or n.get('term', '') or n.get('definition', '') for n in sf['nodes']]
        sf['_embeddings'] = model.encode(texts)
    
    query_embedding = model.encode([query])[0]
    
    # Cosine similarity
    from sklearn.metrics.pairwise import cosine_similarity
    similarities = cosine_similarity([query_embedding], sf['_embeddings'])[0]
    
    matches = []
    for i, sim in enumerate(similarities):
        if sim > threshold:
            matches.append((sf['nodes'][i], round(float(sim), 3)))
    
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches
```

### Integração com sf_matcher

```python
def find_nodes(query, sf, threshold=0.4):
    # ... camadas 1-3 existentes ...
    
    # Camada 4: embeddings (opcional, fallback se não disponível)
    embedding_matches = match_by_embedding(query, sf)
    for node, score in embedding_matches:
        if node["id"] not in seen_ids:
            result.append(node)
            seen_ids.add(node["id"])
    
    return result
```

### Custo de implementação

- **2 dias** para Camada 4 opcional
- **0 dias** se usar sentence-transformers (local, sem API)
- **0 custo** se usar modelo local
- **~$0.01/video** se usar API (para 26 vídeos)

## Decisão

Documentado como plano. Implementar quando necessário — provavelmente quando o matching keyword falhar em casos reais de uso do Chavruta.
