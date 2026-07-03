#!/usr/bin/env python3
"""Computes a structural determinism/subjectivity score from generated
chapter files. Pure markdown parsing — no LLM calls, no semantic judgment."""

import re
import sys
import json
from pathlib import Path

SOP_HEADING = re.compile(r'^### SOP:\s*.+$', re.MULTILINE)
HEURISTICS_SECTION = re.compile(
    r'^## Heuristics \(under uncertainty\)\s*\n(.*?)(?=^## |\Z)',
    re.MULTILINE | re.DOTALL
)
HEURISTIC_BULLET = re.compile(r'^- ', re.MULTILINE)

def _strip_code_fences(text: str) -> str:
    return re.sub(r'```.*?```', '', text, flags=re.DOTALL)

def score_chapter(text: str) -> dict:
    text = _strip_code_fences(text)
    n_sops = len(SOP_HEADING.findall(text))
    heuristics_block = HEURISTICS_SECTION.search(text)
    n_heuristics = (
        len(HEURISTIC_BULLET.findall(heuristics_block.group(1)))
        if heuristics_block else 0
    )
    denom = n_sops + n_heuristics
    pct = (n_sops / denom) if denom > 0 else None
    return {"n_sops": n_sops, "n_heuristics": n_heuristics, "determinism_pct": pct}

def score_skill(chapters_dir: Path) -> dict:
    per_chapter = {}
    total_sops = total_heur = 0
    chapters_with_signal = 0
    files = sorted(list(chapters_dir.glob("ch*.md")) + list(chapters_dir.glob("mod*.md")))

    for f in files:
        result = score_chapter(f.read_text(encoding="utf-8"))
        per_chapter[f.name] = result
        total_sops += result["n_sops"]
        total_heur += result["n_heuristics"]
        if result["determinism_pct"] is not None:
            chapters_with_signal += 1

    denom = total_sops + total_heur
    book_pct = (total_sops / denom) if denom > 0 else None

    return {
        "book_determinism_pct": book_pct,
        "total_sops": total_sops,
        "total_heuristics": total_heur,
        "chapters_total": len(files),
        "chapters_with_procedural_signal": chapters_with_signal,
        "coverage_pct": (chapters_with_signal / len(files)) if files else None,
        "per_chapter": per_chapter,
    }

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: determinism_score.py <skill_dir>", file=sys.stderr)
        sys.exit(1)

    skill_dir = Path(sys.argv[1])
    chapters_dir = skill_dir / "chapters"
    if not chapters_dir.is_dir():
        print(f"No chapters/ found in {skill_dir}", file=sys.stderr)
        sys.exit(1)

    result = score_skill(chapters_dir)
    out_path = skill_dir / "determinism_score.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
