#!/usr/bin/env python3
"""Sessão 6: Aplicação — O fechamento do ciclo.

Estado de aplicação + reflexão.

Perguntas:
  - "Como isso muda sua prática?"
  - "Qual é o próximo passo concreto?"
  - "O que você vai aplicar hoje?"
  - "O que ainda não entendeu?"

Output: application_log.json (session_id, applied_actions, open_questions,
        next_step, reflection)

Stateful: cada sessão futura consulta o application_log para evitar repetir.

Referência judaica: "Sabedoria que não vira vida, para no papel."
                     "Discuta, ensine e aplique."
                     "Sempre pergunte: o que posso fazer com o que aprendi hoje?"
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def create_application_log(
    skill_dir: str,
    applied_actions: list[str] | None = None,
    open_questions: list[str] | None = None,
    next_step: str = "",
    reflection: str = "",
) -> dict:
    """Create application_log.json for Session 6.

    Returns the created application log dict.
    """
    log = {
        "session": 6,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "applied_actions": applied_actions or [],
        "open_questions": open_questions or [],
        "next_step": next_step,
        "reflection": reflection,
    }

    out_dir = Path(skill_dir) / "teach"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "application_log.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    return log


def load_application_log(skill_dir: str) -> dict | None:
    """Load existing application_log.json."""
    path = Path(skill_dir) / "teach" / "application_log.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_aplicacao_prompt(skill_dir: str) -> str:
    """Generate the application prompt for Session 6."""
    existing = load_application_log(skill_dir)
    if existing:
        actions = existing.get("applied_actions", [])
        return (
            "Sessão 6 já completada. "
            f"Ações aplicadas: {len(actions)}\n"
            "Deseja adicionar novas aplicações ou revisar?"
        )

    return (
        "Sessão 6: APLICAÇÃO — O fechamento do ciclo.\n\n"
        "Perguntas:\n"
        "1. Como isso muda sua prática?\n"
        "2. Qual é o próximo passo concreto?\n"
        "3. O que você vai aplicar hoje?\n"
        "4. O que ainda não entendeu?\n\n"
        "Referência: 'Sabedoria que não vira vida, para no papel.'"
    )


def get_open_questions_from_all_sessions(skill_dir: str) -> list[str]:
    """Collect open questions from all sessions for review."""
    all_questions = []

    # From application log
    app_log = load_application_log(skill_dir)
    if app_log:
        all_questions.extend(app_log.get("open_questions", []))

    # From emerging questions
    eq_path = Path(skill_dir) / "emerging_questions" / "emerging_questions.candidates.jsonl"
    if eq_path.exists():
        with open(eq_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    all_questions.append(entry.get("question", ""))

    return all_questions
