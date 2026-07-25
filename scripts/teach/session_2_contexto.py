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


def build_evidence_ledger_from_context(skill_dir: str) -> dict | None:
    """Build evidence_ledger.json from context questions + compilation data.

    This is the GATE: no claim published without evidence_id.
    """
    context = load_context_questions(skill_dir)
    if not context:
        return None

    # Try to load compilation data for principles
    compilation_dir = Path(skill_dir) / "compilation"
    principles = []
    if compilation_dir.exists():
        for json_file in compilation_dir.glob("*.json"):
            if json_file.name.startswith("run") or "semantic_field" in json_file.name:
                continue
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                for p in data.get("principles", []):
                    p["_source_file"] = json_file.name
                    principles.append(p)
            except (json.JSONDecodeError, OSError):
                continue

    # Build ledger entries from principles
    entries = []
    for p in principles:
        statement = p.get("statement", "")
        if not statement:
            continue
        import hashlib
        entry_id = f"ev-{hashlib.sha256(statement.encode()).hexdigest()[:12]}"
        entries.append({
            "entry_id": entry_id,
            "claim": statement,
            "source_file": p.get("_source_file", ""),
            "epistemic_status": p.get("epistemic_status", "speculative"),
            "evidence_text": p.get("evidence", ""),
            "context_author": context.get("author", ""),
            "context_audience": context.get("audience", ""),
            "context_purpose": context.get("purpose", ""),
        })

    ledger = {
        "version": "1.0",
        "session": 2,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
        "metadata": {
            "total_entries": len(entries),
            "context_author": context.get("author", ""),
        },
    }

    # Write to evidence directory
    out_dir = Path(skill_dir) / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "evidence_ledger.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)

    return ledger


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
