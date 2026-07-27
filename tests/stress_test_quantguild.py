#!/usr/bin/env python3
"""QuantGuild stress test for Camada 4 vs Lexical (production-scale SF).

Builds SF from QuantGuild compilation JSONs, runs queries with CORRECT
success criterion: compares returned node against expected term/description.

Requires: pip install sentence-transformers numpy
"""
import json
import glob
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "scripts")

from chavruta.sf_embeddings import DEFAULT_MODEL, embed_sf, match_by_embedding
from chavruta.sf_matcher import find_best_match


def _slugify(text: str) -> str:
    """Simple slug: lowercase, alphanumerics only, max 12 chars."""
    return re.sub(r'[^a-z0-9]', '', text.lower())[:12]


def build_quantguild_sf():
    """Build semantic field from QuantGuild compilations.

    ID strategy: {type}:{source_prefix}:{slugified_term}
    This prevents ID collisions when multiple concepts come from the same source.
    """
    files = glob.glob("output/quantguild_transcripts/compilation/*.json")
    files = [f for f in files if "cross_analysis" not in f]

    concepts, principles, sops = [], [], []

    for f in sorted(files):
        with open(f) as fh:
            data = json.load(fh)
        source = data.get("source", f.split("/")[-1])[:8]

        for c in data.get("concepts", []):
            if isinstance(c, dict):
                term = c.get("name", c.get("term", ""))
                slug = _slugify(term) if term else _slugify(c.get("definition", ""))[:12]
                concepts.append({
                    "id": f"concept:{source}:{slug}",
                    "type": "concept",
                    "term": term,
                    "definition": c.get("definition", ""),
                    "statement": c.get("statement", ""),
                })
        for p in data.get("principles", []):
            if isinstance(p, dict):
                stmt = p.get("statement", p.get("text", ""))
                slug = _slugify(stmt)[:12]
                principles.append({
                    "id": f"principle:{source}:{slug}",
                    "type": "principle",
                    "statement": stmt,
                    "epistemic_status": p.get("epistemic_status", "probable"),
                })
        for s in data.get("sops", []):
            if isinstance(s, dict):
                steps = s.get("steps", s.get("statement", ""))
                name = s.get("name", s.get("title", ""))
                slug = _slugify(name) if name else _slugify(str(steps))[:12]
                sops.append({
                    "id": f"sop:{source}:{slug}",
                    "type": "sop",
                    "term": name,
                    "statement": str(steps)[:200] if steps else "",
                })

    def dedup(nodes):
        seen = set()
        return [n for n in nodes if n["id"] not in seen and not seen.add(n["id"])]

    return {"nodes": dedup(concepts + principles + sops), "edges": []}


def _node_matches_expected(node: dict | None, expected_keywords: list[str]) -> bool:
    """Check if a node matches expected keywords (case-insensitive).

    Returns True if ANY expected keyword appears in the node's text fields.
    """
    if node is None:
        return False
    text = " ".join([
        node.get("id", ""),
        node.get("term", ""),
        node.get("definition", ""),
        node.get("statement", ""),
        node.get("name", ""),
    ]).lower()
    return any(kw.lower() in text for kw in expected_keywords)


def run_test():
    sf = build_quantguild_sf()
    nodes = sf["nodes"]
    print(f"QuantGuild SF: {len(nodes)} nodes")

    t0 = time.perf_counter()
    embed_sf(sf, DEFAULT_MODEL)
    print(f"Warmup: {(time.perf_counter() - t0) * 1000:.0f}ms")
    print()

    # Queries: (query, expected_keywords, is_negative)
    # expected_keywords: list of terms that should appear in the correct node
    queries = [
        ("tail risk protection", ["tail risk", "black swan"], False),
        ("geometric return reduction", ["volatility drag", "geometric"], False),
        ("excess return over benchmark", ["alpha", "excess return", "benchmark"], False),
        ("non-linear wealth growth", ["convexity", "non-linear", "wealth"], False),
        ("market pricing expectations", ["expectations", "pricing", "market"], False),
        ("how to survive a market crash", ["crash", "survive", "black swan", "tail risk"], False),
        ("why losses hurt more than gains help", ["volatility drag", "loss", "losses", "hurt"], False),
        ("what makes a strategy truly profitable", ["alpha", "profit", "strategy"], False),
        ("position sizing for large accounts", ["kelly", "position sizing", "sizing", "fraction"], False),
        ("when to increase leverage", ["leverage", "convexity", "position"], False),
        ("how do professionals manage drawdown", ["drawdown", "risk", "management"], False),
        ("what is the optimal fraction to bet", ["kelly", "fraction", "bet", "optimal"], False),
        ("Volatility Drag", ["volatility drag"], False),
        ("Black Swan", ["black swan"], False),
        ("cooking recipes", [], True),
        ("real estate investment", [], True),
        ("machine learning tutorial", [], True),
        ("how to learn python", [], True),
    ]

    THRESHOLD = 0.50

    print(f"{'#':<3} {'Query':<42} {'Lex':<30} {'Emb':<8} {'Emb match':<30} {'Status'}")
    print("-" * 125)

    lex_excl = emb_excl = both = both_wrong = fp = 0
    lex_correct = emb_correct = 0

    for i, (q, expected, is_neg) in enumerate(queries, 1):
        node_lex, _ = find_best_match(q, sf)
        lex_id = node_lex["id"] if node_lex else None

        emb_matches = match_by_embedding(q, sf, threshold=THRESHOLD, model_name=DEFAULT_MODEL)
        emb_node = emb_matches[0][0] if emb_matches else None
        emb_score = emb_matches[0][1] if emb_matches else 0.0
        emb_id = emb_node["id"] if emb_node else None

        if is_neg:
            # Negative: correct means NO match
            lex_ok = lex_id is None
            emb_ok = emb_id is None
        else:
            # Positive: correct means matched node contains expected keywords
            lex_ok = _node_matches_expected(node_lex, expected)
            emb_ok = _node_matches_expected(emb_node, expected)
            if lex_ok:
                lex_correct += 1
            if emb_ok:
                emb_correct += 1

        if lex_ok and emb_ok:
            status, both = "both OK", both + 1
        elif lex_ok:
            status, lex_excl = "lex only", lex_excl + 1
        elif emb_ok:
            status, emb_excl = "emb only", emb_excl + 1
        else:
            status, both_wrong = "BOTH FAIL", both_wrong + 1

        if is_neg and emb_id and emb_score >= THRESHOLD:
            fp += 1
            status += " FP!"

        lex_display = f"{(lex_id or '—')[:28]}"
        emb_display = f"{(emb_id or '—')[:28]}"
        print(f"{i:<3} {q:<42} {lex_display:<30} {emb_score:<8.3f} {emb_display:<30} {status}")

    print()
    print(f"=== Placar (criterio: keyword match no nó esperado, threshold={THRESHOLD}) ===")
    print(f"Lexical correct:   {lex_correct}/{len(queries) - 4}")
    print(f"Embeddings correct: {emb_correct}/{len(queries) - 4}")
    print(f"Lexical exclusive:  {lex_excl}")
    print(f"Embeddings exclusive: {emb_excl}")
    print(f"Both correct:       {both}")
    print(f"Both wrong:         {both_wrong}")
    print(f"False positives:    {fp}")

    # Below-threshold analysis
    print()
    print("=== Análise abaixo do threshold (0.30-0.50) ===")
    below = 0
    for q, expected, is_neg in queries:
        if is_neg:
            continue
        emb_matches = match_by_embedding(q, sf, threshold=0.30, model_name=DEFAULT_MODEL)
        for node, score in emb_matches:
            if 0.30 < score <= 0.50 and _node_matches_expected(node, expected):
                below += 1
                print(f"  '{q}' → {node['id'][:30]} (score={score:.3f})")
                break
    print(f"  Total above 0.30 but below 0.50: {below}")


if __name__ == "__main__":
    run_test()
