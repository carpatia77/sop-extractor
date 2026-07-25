#!/usr/bin/env python3
"""Sessão 5: Conclusões — Publicação canônica.

Revisão + publicação do Semantic Field.

Processo:
  - Usuário revisa candidatos por status
  - Aprova, rejeita, reduz escopo, marca como não_sei
  - Validators executam todos os gates
  - Publica semantic_field.json + semantic_field.md
  - Publica emerging_questions.md

Output: artefatos canônicos (só itens aprovados)

Gate: nenhum proposed/rejected aparece no canônico.

Referência judaica: "Escreva com suas próprias palavras.
                     Crie conexões. Estruture e tire conclusões."
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_candidates(skill_dir: str) -> list[dict]:
    """Load candidates from semantic_field.candidates.jsonl."""
    path = Path(skill_dir) / "semantic_field" / "semantic_field.candidates.jsonl"
    if not path.exists():
        return []

    candidates = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))
    return candidates


def filter_approved(candidates: list[dict]) -> list[dict]:
    """Filter candidates to only approved items."""
    return [c for c in candidates if c.get("status") == "approved"]


def publish_semantic_field(skill_dir: str, candidates: list[dict] | None = None) -> Path:
    """Publish candidates as semantic_field.json.

    Auto-filters: only items with status="approved" are published.
    proposed/rejected items are NEVER included — this is the core
    anti-fabrication gate.
    """
    if candidates is None:
        candidates = load_candidates(skill_dir)

    # GATE: only approved items reach the canonical output
    approved = filter_approved(candidates)

    out_dir = Path(skill_dir) / "semantic_field"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "semantic_field.json"

    sf = {
        "version": "1.0",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "nodes": [c for c in approved if c.get("type") in ("concept", "principle", "sop", "reference")],
        "edges": [c for c in approved if c.get("type") == "edge"],
        "metadata": {
            "total_nodes": len([c for c in approved if c.get("type") != "edge"]),
            "total_edges": len([c for c in approved if c.get("type") == "edge"]),
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sf, f, indent=2, ensure_ascii=False)

    return out_path


def generate_conclusoes_prompt(skill_dir: str) -> str:
    """Generate the conclusion prompt for Session 5."""
    candidates = load_candidates(skill_dir)
    approved = [c for c in candidates if c.get("status") == "approved"]
    rejected = [c for c in candidates if c.get("status") == "rejected"]

    return (
        f"Sessão 5: CONCLUSÕES — Publicação canônica.\n\n"
        f"Candidatos: {len(candidates)} total, "
        f"{len(approved)} aprovados, {len(rejected)} rejeitados.\n\n"
        "Revise cada candidato e decida:\n"
        "- Aprovar (adicionar ao canônico)\n"
        "- Rejeitar (não incluir)\n"
        "- Reduzir escopo (marcar como suposição)\n"
        "- Não sei (marcar para revisão futura)\n\n"
        "Gate: nenhum proposed/rejected aparece no canônico."
    )
