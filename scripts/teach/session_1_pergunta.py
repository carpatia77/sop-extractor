#!/usr/bin/env python3
"""Sessão 1: Pergunta — Ative o cérebro.

Entrevista o usuário ANTES de compilar. Gera task_contract.json.

Perguntas:
  - "O que você quer entender nesta obra?"
  - "Qual problema você tenta resolver?"
  - "Você quer fundamentos ou procedimentos?"
  - "Tem fontes complementares para cruzar?"

Output: task_contract.json (user_goal, intended_outcome, interpretation, ambiguity_status)

Referência judaica: "Uma pergunta boa abre um estudo bom."
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def create_task_contract(
    skill_dir: str,
    user_goal: str,
    intended_outcome: str = "",
    interpretation: str = "",
    ambiguity_status: str = "resolved",
    complementary_sources: list[str] | None = None,
) -> dict:
    """Create a task_contract.json for Session 1.

    Args:
        skill_dir: path to the skill workspace directory
        user_goal: what the user wants to understand
        intended_outcome: what they expect to get
        interpretation: how they interpret the source
        ambiguity_status: resolved | partial | unresolved
        complementary_sources: optional list of additional sources

    Returns:
        The created task contract dict.
    """
    contract = {
        "session": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_goal": user_goal,
        "intended_outcome": intended_outcome,
        "interpretation": interpretation,
        "ambiguity_status": ambiguity_status,
        "complementary_sources": complementary_sources or [],
        "foundation_or_procedures": "",  # filled by user
    }

    # Write to disk
    out_dir = Path(skill_dir) / "teach"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "task_contract.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=2, ensure_ascii=False)

    return contract


def load_task_contract(skill_dir: str) -> dict | None:
    """Load existing task_contract.json."""
    path = Path(skill_dir) / "teach" / "task_contract.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_pergunta_prompt(skill_dir: str) -> str:
    """Generate the interview prompt for Session 1.

    Returns a list of questions for the user to answer.
    """
    questions = [
        "O que você quer entender nesta obra?",
        "Qual problema você tenta resolver?",
        "Você quer fundamentos ou procedimentos?",
        "Tem fontes complementares para cruzar?",
    ]

    existing = load_task_contract(skill_dir)
    if existing:
        return (
            "Sessão 1 já iniciada. Goal atual: "
            f"{existing.get('user_goal', '(não definido)')}\n"
            "Deseja revisar ou confirmar?"
        )

    prompt = "Sessão 1: PERGUNTA — Antes de compilar, preciso entender seu objetivo.\n\n"
    for i, q in enumerate(questions, 1):
        prompt += f"{i}. {q}\n"

    return prompt
