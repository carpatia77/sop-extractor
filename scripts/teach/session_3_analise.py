#!/usr/bin/env python3
"""Sessão 3: Análise — A verdade se afia.

Coherence audit + Evolution audit + Refutation chain.

Perguntas:
  - "O autor contradiz a si mesmo?"
  - "Onde a doutrina mudou ao longo do tempo?"
  - "Há tensões não resolvidas?"
  - "O que outra fonte diz sobre o mesmo tema?"

Output: coherence_audit.md + evolution audit (contradictions flagged, tensions opened)

Gate: Contradições não são reconciliadas silenciosamente.

Referência judaica: "Comparar não confunde, aprofunda."
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def run_coherence_check(skill_dir: str) -> dict:
    """Run coherence audit on compiled principles.

    Checks for internal contradictions within the same source.
    Returns audit results.
    """
    compilation_dir = Path(skill_dir) / "compilation"
    if not compilation_dir.exists():
        return {"error": "no compilation directory found"}

    contradictions = []
    for json_file in compilation_dir.glob("*.json"):
        if json_file.name.startswith("run") or "semantic_field" in json_file.name:
            continue
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            principles = data.get("principles", [])
            # Simple coherence check: flag principles with dissent_type "contradicts"
            for p in principles:
                refutation = p.get("refutation", {})
                if refutation.get("dissent_type") == "contradicts":
                    contradictions.append({
                        "file": json_file.name,
                        "statement": p.get("statement", ""),
                        "contradiction": refutation.get("strongest_alternative", ""),
                    })
        except (json.JSONDecodeError, OSError):
            continue

    return {
        "session": 3,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "contradictions_found": len(contradictions),
        "contradictions": contradictions,
    }


def generate_analise_prompt(skill_dir: str) -> str:
    """Generate the analysis prompt for Session 3."""
    return (
        "Sessão 3: ANÁLISE — A verdade se afia na comparação.\n\n"
        "Perguntas:\n"
        "1. O autor contradiz a si mesmo?\n"
        "2. Onde a doutrina mudou ao longo do tempo?\n"
        "3. Há tensões não resolvidas?\n"
        "4. O que outra fonte diz sobre o mesmo tema?\n\n"
        "Gate: Contradições NÃO são reconciliadas silenciosamente."
    )


def save_coherence_audit(skill_dir: str, audit: dict) -> Path:
    """Save coherence audit results."""
    out_dir = Path(skill_dir) / "teach"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "coherence_audit.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)

    return out_path
