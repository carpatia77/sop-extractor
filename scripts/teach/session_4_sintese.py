#!/usr/bin/env python3
"""Sessão 4: Síntese — Você processa, não é esponja.

Gera candidatos para o Semantic Field.

Processo:
  - LLM propõe nós (conceitos, métricas, mecanismos)
  - LLM propõe arestas (relações do vocabulário fechado)
  - Cada item classificado: certo / provável / suposição / não_sei
  - Auto-ataque para claims causais e quantitativos
  - Perguntas emergentes apenas de lacuna, tensão ou limite

Output: semantic_field.candidates.jsonl + emerging_questions.candidates.jsonl

Gate: Nada publicado sem epistemic_status + evidence_ids.

Referência judaica: "Você não é uma esponja; é um processador."
"""
from __future__ import annotations

import json
from pathlib import Path


def generate_sintese_prompt(skill_dir: str) -> str:
    """Generate the synthesis prompt for Session 4."""
    return (
        "Sessão 4: SÍNTESE — Você processa, não é esponja.\n\n"
        "A partir da evidence_ledger e dos audits, gere candidatos para o Semantic Field:\n"
        "1. Conceitos-chave (com definições)\n"
        "2. Princípios (com epistemic_status: certo/provável/suposição)\n"
        "3. SOPs (quando aplicar)\n"
        "4. Referências (autores, papers, modelos)\n"
        "5. Relações entre nós (used_in, supports, requires, references)\n\n"
        "Cada candidato DEVE ter epistemic_status e evidence_id.\n"
        "Gate: NADA é publicado sem evidência."
    )


def create_candidates_file(skill_dir: str, candidates: list[dict]) -> Path:
    """Write candidates to semantic_field.candidates.jsonl."""
    out_dir = Path(skill_dir) / "semantic_field"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "semantic_field.candidates.jsonl"

    with open(out_path, "w", encoding="utf-8") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    return out_path


def create_emerging_questions(skill_dir: str, questions: list[str]) -> Path:
    """Write emerging questions to candidates file."""
    out_dir = Path(skill_dir) / "emerging_questions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "emerging_questions.candidates.jsonl"

    with open(out_path, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps({"question": q, "source": "session_4"}, ensure_ascii=False) + "\n")

    return out_path
