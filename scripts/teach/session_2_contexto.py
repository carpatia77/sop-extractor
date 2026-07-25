#!/usr/bin/env python3
"""Sessão 2: Contexto — Leitura atenta + contexto.

Pre-flight scan + extração determinística. Gera evidence_ledger.json.

Perguntas contextuais (gate obrigatório):
  - "Quem é o autor? Qual sua autoridade?"
  - "Para quem foi escrito?"
  - "Em que momento histórico?"
  - "Qual o propósito do autor?"

Output: evidence_ledger.json (source_id, source_date, locator, excerpt_hash)

Referência judaica: "Nenhuma palavra é neutra." / "Texto sem contexto gera leitura rasa."
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def create_context_questions(
    skill_dir: str,
    author: str = "",
    authority: str = "",
    audience: str = "",
    historical_context: str = "",
    purpose: str = "",
) -> dict:
    """Create context_questions.json for Session 2.

    Returns the created context dict.
    """
    context = {
        "session": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "author": author,
        "authority": authority,
        "audience": audience,
        "historical_context": historical_context,
        "purpose": purpose,
    }

    out_dir = Path(skill_dir) / "teach"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "context_questions.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    return context


def load_context_questions(skill_dir: str) -> dict | None:
    """Load existing context_questions.json."""
    path = Path(skill_dir) / "teach" / "context_questions.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_contexto_prompt(skill_dir: str) -> str:
    """Generate the context questions for Session 2."""
    questions = [
        "Quem é o autor? Qual sua autoridade?",
        "Para quem foi escrito?",
        "Em que momento histórico?",
        "Qual o propósito do autor?",
    ]

    existing = load_context_questions(skill_dir)
    if existing:
        author = existing.get("author", "")
        return (
            "Sessão 2 já iniciada. "
            f"Autor: {author or '(não definido)'}\n"
            "Deseja revisar o contexto?"
        )

    prompt = "Sessão 2: CONTEXTO — Antes de analisar, preciso entender a fonte.\n\n"
    for i, q in enumerate(questions, 1):
        prompt += f"{i}. {q}\n"

    return prompt
