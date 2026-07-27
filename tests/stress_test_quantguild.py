#!/usr/bin/env python3
"""QuantGuild stress test for Camada 4 vs Lexical (72-node SF).

Builds SF from 28 QuantGuild compilation JSONs, runs 18 queries.
Requires: pip install sentence-transformers numpy
"""
import json
import glob
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "scripts")

from chavruta.sf_embeddings import DEFAULT_MODEL, embed_sf, match_by_embedding
from chavruta.sf_matcher import find_best_match, match_by_salient


def build_quantguild_sf():
    """Build semantic field from QuantGuild compilations."""
    files = glob.glob("output/quantguild_transcripts/compilation/*.json")
    files = [f for f in files if "cross_analysis" not in f]

    concepts, principles, sops = [], [], []

    for f in sorted(files):
        with open(f) as fh:
            data = json.load(fh)
        source = data.get("source", f.split("/")[-1])[:8]

        for c in data.get("concepts", []):
            if isinstance(c, dict):
                concepts.append({
                    "id": f"concept:{source}",
                    "type": "concept",
                    "term": c.get("name", c.get("term", "")),
                    "definition": c.get("definition", ""),
                    "statement": c.get("statement", ""),
                })
        for p in data.get("principles", []):
            if isinstance(p, dict):
                principles.append({
                    "id": f"principle:{source}",
                    "type": "principle",
                    "statement": p.get("statement", p.get("text", "")),
                    "epistemic_status": p.get("epistemic_status", "probable"),
                })
        for s in data.get("sops", []):
            if isinstance(s, dict):
                steps = s.get("steps", s.get("statement", ""))
                sops.append({
                    "id": f"sop:{source}",
                    "type": "sop",
                    "term": s.get("name", s.get("title", "")),
                    "statement": str(steps)[:200] if steps else "",
                })

    def dedup(nodes):
        seen = set()
        return [n for n in nodes if n["id"] not in seen and not seen.add(n["id"])]

    return {"nodes": dedup(concepts + principles + sops), "edges": []}


def run_test():
    sf = build_quantguild_sf()
    nodes = sf["nodes"]
    print(f"QuantGuild SF: {len(nodes)} nodes")

    t0 = time.perf_counter()
    embed_sf(sf, DEFAULT_MODEL)
    print(f"Warmup: {(time.perf_counter() - t0) * 1000:.0f}ms")
    print()

    queries = [
        ("tail risk protection", "conceito: black swan"),
        ("geometric return reduction", "conceito: volatility drag"),
        ("excess return over benchmark", "conceito: alpha"),
        ("non-linear wealth growth", "conceito: convexity"),
        ("market pricing expectations", "conceito: expectations"),
        ("how to survive a market crash", "paráfrase de black swan"),
        ("why losses hurt more than gains help", "paráfrase de volatility drag"),
        ("what makes a strategy truly profitable", "paráfrase de alpha"),
        ("position sizing for large accounts", "paráfrase de Kelly"),
        ("when to increase leverage", "paráfrase de convexity"),
        ("how do professionals manage drawdown", "paráfrase de risk management"),
        ("what is the optimal fraction to bet", "paráfrase de Kelly criterion"),
        ("Volatility Drag", "substring exato"),
        ("Black Swan", "substring exato"),
        ("cooking recipes", "NEGATIVO"),
        ("real estate investment", "NEGATIVO"),
        ("machine learning tutorial", "NEGATIVO"),
        ("how to learn python", "NEGATIVO"),
    ]

    print(f"{'#':<3} {'Query':<42} {'Lex':<25} {'Emb':<8} {'Emb match':<25} {'Status'}")
    print("-" * 115)

    lex_excl = emb_excl = both = both_wrong = fp = 0

    for i, (q, desc) in enumerate(queries, 1):
        node_lex, _ = find_best_match(q, sf)
        lex_id = node_lex["id"] if node_lex else None
        salient = match_by_salient(q, nodes, threshold=0.0)
        lex_score = salient[0][1] if salient else 0.0

        emb_matches = match_by_embedding(q, sf, threshold=0.0, model_name=DEFAULT_MODEL)
        emb_node = emb_matches[0][0] if emb_matches else None
        emb_score = emb_matches[0][1] if emb_matches else 0.0
        emb_id = emb_node["id"] if emb_node else None

        is_neg = "NEGATIVO" in desc
        lex_ok = (lex_id is None) if is_neg else (lex_id is not None)
        emb_ok = (emb_id is None) if is_neg else (emb_id is not None)

        if lex_ok and emb_ok:
            status, both = "both OK", both + 1
        elif lex_ok:
            status, lex_excl = "lex only", lex_excl + 1
        elif emb_ok:
            status, emb_excl = "emb only", emb_excl + 1
        else:
            status, both_wrong = "BOTH FAIL", both_wrong + 1

        if is_neg and emb_id and emb_score >= 0.50:
            fp += 1
            status += " FP!"

        print(f"{i:<3} {q:<42} {(lex_id or '—'):<25} {emb_score:<8.3f} {(emb_id or '—'):<25} {status}")

    print()
    print(f"Lexical exclusive:  {lex_excl}")
    print(f"Embeddings exclusive: {emb_excl}")
    print(f"Both correct:       {both}")
    print(f"Both wrong:         {both_wrong}")
    print(f"False positives:    {fp}")


if __name__ == "__main__":
    run_test()
