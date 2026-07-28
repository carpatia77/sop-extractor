#!/usr/bin/env python3
"""Validates a semantic_field.json file against structural and anti-hallucination rules.

Usage:
    python scripts/validate_semantic_field.py <sf_json_path> [--require-evidence]
"""

import json
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from semantic_field import validate_semantic_field


def main():
    parser = argparse.ArgumentParser(description="Validate a semantic field JSON file.")
    parser.add_argument("sf_path", help="Path to semantic_field.json")
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="Require evidence_id on every node (anti-hallucination gate)",
    )
    args = parser.parse_args()

    try:
        with open(args.sf_path, "r", encoding="utf-8") as f:
            sf = json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {args.sf_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}")
        sys.exit(1)

    errors = validate_semantic_field(sf, require_evidence=args.require_evidence)

    if errors:
        print(f"Semantic field validation failed ({len(errors)} error(s)):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        n_nodes = len(sf.get("nodes", []))
        n_edges = len(sf.get("edges", []))
        print(f"Semantic field is valid ({n_nodes} nodes, {n_edges} edges).")
        sys.exit(0)


if __name__ == "__main__":
    main()
