#!/usr/bin/env python3
"""SF Matcher — multi-layer node matching against Semantic Field.

Solves the "find_node" problem: matching natural language queries against
graph nodes. Four layers, from exact to semantic:

  1. Exact ID match (e.g. "principle:abc123")
  2. Substring match in statement/term/definition
  3. Salient-term Jaccard overlap (threshold 0.4)
  4. Embedding cosine similarity (optional, fallback if unavailable)

Used by:
  - drift_detector.py: checks if user response maps to SF nodes
  - depth_tracker.py: checks if response references SF concepts
  - chavruta engine: locates claims in the knowledge graph
  - semantic_guard.py: type confusion detection
"""
from __future__ import annotations

try:
    from scripts.verify_concept_presence import salient_terms
except ImportError:
    from verify_concept_presence import salient_terms

try:
    from scripts.chavruta.sf_embeddings import match_by_embedding, is_available as embeddings_available
except ImportError:
    try:
        from chavruta.sf_embeddings import match_by_embedding, is_available as embeddings_available
    except ImportError:
        match_by_embedding = None
        def embeddings_available() -> bool:
            return False


# ---------------------------------------------------------------------------
# Layer 1: Exact ID match
# ---------------------------------------------------------------------------

def match_by_id(query: str, nodes: list[dict]) -> dict | None:
    """Match a query against node IDs exactly.

    Query "principle:abc123" returns the node with id "principle:abc123".
    """
    q = query.strip()
    for node in nodes:
        if node.get("id") == q:
            return node
    return None


# ---------------------------------------------------------------------------
# Layer 2: Substring match
# ---------------------------------------------------------------------------

def match_by_substring(query: str, nodes: list[dict]) -> list[dict]:
    """Match query as substring in statement, term, or definition.

    Returns all nodes where query appears (case-insensitive).
    """
    q = query.lower().strip()
    if not q:
        return []
    matches = []
    for node in nodes:
        text = " ".join([
            node.get("statement", ""),
            node.get("term", ""),
            node.get("definition", ""),
            node.get("name", ""),
            node.get("when_to_use", ""),
        ]).lower()
        if q in text:
            matches.append(node)
    return matches


# ---------------------------------------------------------------------------
# Layer 3: Salient-term Jaccard overlap
# ---------------------------------------------------------------------------

def match_by_salient(
    query: str,
    nodes: list[dict],
    threshold: float = 0.4,
) -> list[tuple[dict, float]]:
    """Match query against nodes using overlap coefficient.

    Uses overlap coefficient (|A∩B| / min(|A|,|B|)) instead of Jaccard
    to avoid dilution from connector words in natural language.
    Frases naturais não diluem mais o denominator.

    Returns list of (node, overlap_score) tuples, sorted by score descending.
    Only includes nodes with overlap > threshold.
    """
    query_terms = set(salient_terms(query))
    if not query_terms:
        return []

    matches = []
    for node in nodes:
        text = " ".join([
            node.get("statement", ""),
            node.get("term", ""),
            node.get("definition", ""),
            node.get("name", ""),
        ])
        node_terms = set(salient_terms(text))
        if not node_terms:
            continue
        overlap = len(query_terms & node_terms) / min(len(query_terms), len(node_terms))
        if overlap > threshold:
            matches.append((node, round(overlap, 3)))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Unified matcher (all 3 layers)
# ---------------------------------------------------------------------------

def find_nodes(
    query: str,
    sf: dict,
    threshold: float = 0.4,
    embedding_threshold: float = 0.55,
) -> list[dict]:
    """Find nodes in Semantic Field matching query.

    Combines results from all 4 layers (deduplicated):
      1. Exact ID match (highest priority)
      2. Substring match in statement/term/definition/name
      3. Salient-term Jaccard overlap above threshold
      4. Embedding cosine similarity (optional fallback)

    Returns deduplicated list of matched nodes.
    """
    nodes = sf.get("nodes", [])
    seen_ids = set()
    result = []

    # Layer 1: exact ID
    exact = match_by_id(query, nodes)
    if exact:
        return [exact]

    # Layer 2: substring
    for node in match_by_substring(query, nodes):
        if node["id"] not in seen_ids:
            result.append(node)
            seen_ids.add(node["id"])

    # Layer 3: salient terms (add nodes not already found)
    for node, _score in match_by_salient(query, nodes, threshold):
        if node["id"] not in seen_ids:
            result.append(node)
            seen_ids.add(node["id"])

    # Layer 4: embeddings (optional, silent fallback)
    if match_by_embedding is not None and not result:
        try:
            for node, _score in match_by_embedding(query, sf, embedding_threshold):
                if node["id"] not in seen_ids:
                    result.append(node)
                    seen_ids.add(node["id"])
        except Exception:
            pass  # Embeddings unavailable — layers 1-3 suffice

    return result


def find_best_match(
    query: str,
    sf: dict,
    threshold: float = 0.3,
    embedding_threshold: float = 0.55,
) -> tuple[dict | None, str]:
    """Find the single best matching node.

    Returns (node, match_layer) or (None, "none").
    match_layer is "id", "substring", "salient", "embedding", or "none".
    """
    nodes = sf.get("nodes", [])

    # Layer 1: exact ID
    exact = match_by_id(query, nodes)
    if exact:
        return exact, "id"

    # Layer 2: substring (return first match)
    substr_matches = match_by_substring(query, nodes)
    if substr_matches:
        return substr_matches[0], "substring"

    # Layer 3: salient terms (return best above threshold)
    salient_matches = match_by_salient(query, nodes, threshold)
    if salient_matches:
        return salient_matches[0][0], "salient"

    # Layer 4: embeddings (optional fallback)
    if match_by_embedding is not None:
        try:
            emb_matches = match_by_embedding(query, sf, embedding_threshold)
            if emb_matches:
                return emb_matches[0][0], "embedding"
        except Exception:
            pass

    return None, "none"
