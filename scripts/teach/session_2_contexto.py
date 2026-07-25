#!/usr/bin/env python3
"""Sessão 2: Contexto — Leitura atenta + contexto.

Gera context_questions.json + evidence_ledger.json usando o módulo
canônico evidence_ledger.build_ledger().

Perguntas contextuais (gate obrigatório):
  - "Quem é o autor? Qual sua autoridade?"
  - "Para quem foi escrito?"
  - "Em que momento histórico?"
  - "Qual o propósito do autor?"

Output: evidence_ledger.json (entry_id, claim, locator, excerpt_hash,
        evidence_text, epistemic_status, refutation)

Gate: Nenhum claim sem evidence_id válido.

Referência judaica: "Nenhuma palavra é neutra." / "Texto sem contexto gera leitura rasa."
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.evidence_ledger import build_ledger
except ImportError:
    from evidence_ledger import build_ledger


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

    # Wire: build evidence_ledger.json as part of session 2 output
    build_evidence_ledger(skill_dir)

    return context


def load_context_questions(skill_dir: str) -> dict | None:
    """Load existing context_questions.json."""
    path = Path(skill_dir) / "teach" / "context_questions.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def build_evidence_ledger(skill_dir: str) -> dict | None:
    """Build evidence_ledger.json using the canonical evidence_ledger module.

    This is the GATE: no claim published without evidence_id.
    Uses evidence_ledger.build_ledger() — the real module with locator,
    excerpt_hash, source_sha256, upload_date, refutation fields.
    """
    context = load_context_questions(skill_dir)
    if not context:
        return None

    # Load compilation data for principles
    compilation_dir = Path(skill_dir) / "compilation"
    principles = []
    source_hash = ""
    source_metadata = {
        "upload_date": "",
        "title": context.get("author", ""),
        "uploader": context.get("author", ""),
    }

    if compilation_dir.exists():
        for json_file in compilation_dir.glob("*.json"):
            if json_file.name.startswith("run") or "semantic_field" in json_file.name:
                continue
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                source_hash = data.get("source_sha256", source_hash)
                for p in data.get("principles", []):
                    principles.append(p)
            except (json.JSONDecodeError, OSError):
                continue

    # Use the canonical evidence_ledger module (even with empty principles)
    ledger = build_ledger(
        principles=principles,
        filepath=str(compilation_dir) if compilation_dir.exists() else "",
        source_hash=source_hash,
        source_metadata=source_metadata,
    )

    # Add context metadata
    ledger["context"] = {
        "author": context.get("author", ""),
        "authority": context.get("authority", ""),
        "audience": context.get("audience", ""),
        "historical_context": context.get("historical_context", ""),
        "purpose": context.get("purpose", ""),
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
