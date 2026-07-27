#!/usr/bin/env python3
"""GURPS stress test for Camada 4 (embeddings) vs Lexical (Layers 1-3).

Reproducible: runs against real GURPS semantic field from output/.
Requires: pip install sentence-transformers numpy
"""
import json
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "scripts")

from chavruta.sf_embeddings import DEFAULT_MODEL, embed_sf, match_by_embedding
from chavruta.sf_matcher import find_best_match, match_by_salient


def load_gurps_sf():
    path = "output/gurps/compilation/gurps_basic_set.semantic_field.json"
    with open(path) as f:
        return json.load(f)


def run_test():
    sf = load_gurps_sf()
    nodes = sf["nodes"]
    print(f"SF: {len(nodes)} nodes, {len(sf.get('edges', []))} edges")
    print(f"Model: {DEFAULT_MODEL}")
    print()

    # Warm up
    t0 = time.perf_counter()
    embed_sf(sf, DEFAULT_MODEL)
    print(f"Warmup: {(time.perf_counter() - t0) * 1000:.0f}ms")
    print()

    # Queries: (query, description, expected_correct_node_id_or_None)
    queries = [
        ("armor protection", "sinônimo de DR", "concept:damage-resistance"),
        ("dodge parry block", "sinônimo de Active Defense", "concept:active-defense"),
        ("stamina fatigue", "relacionado a FP", "concept:fatigue-points"),
        ("tech level civilization", "relacionado a TL", "concept:tech-level"),
        ("how hard to hit something", "paráfrase de Skill/Active Defense", "concept:active-defense"),
        ("carrying capacity", "sinônimo de Encumbrance", "concept:encumbrance"),
        ("Damage Resistance", "substring exato", "concept:damage-resistance"),
        ("Active Defense", "substring exato", "concept:active-defense"),
        ("how much punishment can I take", "paráfrase de DR/HP", "concept:damage-resistance"),
        ("movement penalty overencumbered", "paráfrase de Encumbrance", "concept:encumbrance"),
        ("point buy character creation", "paráfrase de point costs", None),
        ("cooking recipes", "NEGATIVO", None),
        ("stock market trading", "NEGATIVO", None),
        ("python programming", "NEGATIVO", None),
    ]

    print(f"{'#':<3} {'Query':<35} {'Lexical':<22} {'Emb':<8} {'Emb match':<22} {'Correct?'}")
    print("-" * 105)

    results = []
    for i, (q, desc, expected) in enumerate(queries, 1):
        # Lexical
        node_lex, layer_lex = find_best_match(q, sf)
        lex_id = node_lex["id"] if node_lex else None

        # Salient score
        salient = match_by_salient(q, nodes, threshold=0.0)
        lex_score = salient[0][1] if salient else 0.0

        # Embeddings
        emb_matches = match_by_embedding(q, sf, threshold=0.0, model_name=DEFAULT_MODEL)
        emb_node = emb_matches[0][0] if emb_matches else None
        emb_score = emb_matches[0][1] if emb_matches else 0.0
        emb_id = emb_node["id"] if emb_node else None

        # Correctness
        if expected:
            lex_correct = lex_id == expected
            emb_correct = emb_id == expected
        else:
            # Negative: correct = no match
            lex_correct = lex_id is None
            emb_correct = emb_id is None

        lex_str = f"{lex_id}" if lex_id else "—"
        emb_str = f"{emb_score:.3f}"
        emb_id_str = f"{emb_id}" if emb_id else "—"

        correct_str = ""
        if lex_correct and emb_correct:
            correct_str = "both OK"
        elif lex_correct:
            correct_str = "lex only"
        elif emb_correct:
            correct_str = "emb only"
        else:
            correct_str = "BOTH WRONG"

        print(f"{i:<3} {q:<35} {lex_str:<22} {emb_str:<8} {emb_id_str:<22} {correct_str}")

        results.append({
            "query": q,
            "desc": desc,
            "expected": expected,
            "lex_id": lex_id,
            "lex_score": lex_score,
            "emb_id": emb_id,
            "emb_score": emb_score,
            "lex_correct": lex_correct,
            "emb_correct": emb_correct,
        })

    # Summary
    print()
    lex_exclusive = sum(1 for r in results if r["lex_correct"] and not r["emb_correct"])
    emb_exclusive = sum(1 for r in results if r["emb_correct"] and not r["lex_correct"])
    both_correct = sum(1 for r in results if r["lex_correct"] and r["emb_correct"])
    both_wrong = sum(1 for r in results if not r["lex_correct"] and not r["emb_correct"])

    print(f"Lexical exclusive wins: {lex_exclusive}")
    print(f"Embeddings exclusive wins: {emb_exclusive}")
    print(f"Both correct: {both_correct}")
    print(f"Both wrong: {both_wrong}")

    # False positives at threshold 0.50
    print()
    fp = 0
    for r in results:
        if r["expected"] is None and r["emb_score"] >= 0.50:
            fp += 1
            print(f"  FP: '{r['query']}' → {r['emb_id']} (score={r['emb_score']:.3f})")
    tp = sum(1 for r in results if r["expected"] and r["emb_score"] >= 0.50)
    print(f"At threshold 0.50: {tp} TP, {fp} FP")


if __name__ == "__main__":
    run_test()
