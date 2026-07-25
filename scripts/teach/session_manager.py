#!/usr/bin/env python3
"""Session Manager — stateful management for 6 Judaic study sessions.

Manages the workspace state across sessions:
  1. Pergunta (task_contract)
  2. Contexto (evidence_ledger)
  3. Análise (coherence + evolution + refutation)
  4. Síntese (SF candidates)
  5. Conclusões (publication)
  6. Aplicação (application_log)

Stateful: each future session consults progress to avoid repetition.
Progressive: depth calibrates based on session completion.

Used by:
  - sopx teach CLI
  - Chavruta Engine (session context)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Session definitions
# ---------------------------------------------------------------------------

SESSIONS = {
    1: {
        "name": "Pergunta",
        "description": "Ative o cérebro — perguntas antes de compilar",
        "input": "obra do autor (PDF, curso, transcrição)",
        "output": "task_contract.json",
        "gate": "Nenhuma compilação começa sem pergunta clara",
    },
    2: {
        "name": "Contexto",
        "description": "Leitura atenta + contexto — quem, para quem, quando",
        "input": "fonte do autor + task_contract",
        "output": "evidence_ledger.json",
        "gate": "Nenhum claim sem evidence_id válido",
    },
    3: {
        "name": "Análise",
        "description": "Análise e comparação — a verdade se afia",
        "input": "evidence_ledger + múltiplas fontes",
        "output": "coherence_audit.md + evolution audit",
        "gate": "Contradições não são reconciliadas silenciosamente",
    },
    4: {
        "name": "Síntese",
        "description": "Você processa — não é esponja",
        "input": "evidence_ledger + audits + task_contract",
        "output": "semantic_field.candidates.jsonl",
        "gate": "Nada publicado sem epistemic_status + evidence_ids",
    },
    5: {
        "name": "Conclusões",
        "description": "Conclusões próprias — publicação canônica",
        "input": "candidatos da sessão 4",
        "output": "semantic_field.json + emerging_questions.md",
        "gate": "nenhum proposed/rejected aparece no canônico",
    },
    6: {
        "name": "Aplicação",
        "description": "Fechamento do ciclo — aplicação + reflexão",
        "input": "artefatos canônicos + sessões anteriores",
        "output": "application_log.json",
        "gate": "Stateful: cada sessão futura consulta o application_log",
    },
}

# File patterns per session
SESSION_FILES = {
    1: ["teach/task_contract.json"],
    2: ["teach/context_questions.json", "evidence/evidence_ledger.json"],
    3: ["teach/coherence_audit.md"],
    4: ["semantic_field/semantic_field.candidates.jsonl"],
    5: ["semantic_field/semantic_field.json", "semantic_field/semantic_field.review.json"],
    6: ["teach/application_log.json"],
}

# Required files for progress tracking
PROGRESS_FILE = "teach/progress.json"
SESSION_LOG_FILE = "teach/session_log.jsonl"


# ---------------------------------------------------------------------------
# Progress management
# ---------------------------------------------------------------------------

def _progress_path(skill_dir: str) -> Path:
    return Path(skill_dir) / PROGRESS_FILE


def _session_log_path(skill_dir: str) -> Path:
    return Path(skill_dir) / SESSION_LOG_FILE


def load_progress(skill_dir: str) -> dict:
    """Load session progress from disk."""
    path = _progress_path(skill_dir)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {
        "current_session": 1,
        "completed_sessions": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_activity": None,
        "session_history": [],
    }


def save_progress(skill_dir: str, progress: dict) -> None:
    """Save session progress to disk."""
    path = _progress_path(skill_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    progress["last_activity"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def log_session(skill_dir: str, session_num: int, action: str, details: dict) -> None:
    """Append to session log (JSONL format)."""
    path = _session_log_path(skill_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session": session_num,
        "action": action,
        **details,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def get_current_session(skill_dir: str) -> int:
    """Get the current session number (1-6)."""
    progress = load_progress(skill_dir)
    return progress.get("current_session", 1)


def get_completed_sessions(skill_dir: str) -> list[int]:
    """Get list of completed session numbers."""
    progress = load_progress(skill_dir)
    return progress.get("completed_sessions", [])


def is_session_completed(skill_dir: str, session_num: int) -> bool:
    """Check if a specific session is completed."""
    return session_num in get_completed_sessions(skill_dir)


def complete_session(skill_dir: str, session_num: int) -> int:
    """Mark a session as completed, return next session number.

    Returns:
        Next session number (1-6), or 0 if all sessions complete.
    """
    progress = load_progress(skill_dir)

    if session_num not in progress["completed_sessions"]:
        progress["completed_sessions"].append(session_num)
        progress["completed_sessions"].sort()

    # Advance to next session
    if session_num < 6:
        progress["current_session"] = session_num + 1
    else:
        progress["current_session"] = 0  # All done

    # Record in history
    progress["session_history"].append({
        "session": session_num,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    save_progress(skill_dir, progress)
    log_session(skill_dir, session_num, "completed", {
        "next_session": progress["current_session"],
    })

    return progress["current_session"]


def start_session(skill_dir: str, session_num: int | None = None) -> dict:
    """Start or resume a session.

    If session_num is None, resumes the current session.
    Returns session info dict.
    """
    progress = load_progress(skill_dir)

    if session_num is None:
        session_num = progress.get("current_session", 1)

    if session_num < 1 or session_num > 6:
        raise ValueError(f"Invalid session number: {session_num}")

    session_info = SESSIONS[session_num].copy()
    session_info["session_number"] = session_num
    session_info["is_resume"] = session_num in progress.get("completed_sessions", [])

    # Check which output files exist
    patterns = SESSION_FILES.get(session_num, [])
    existing_files = []
    for pattern in patterns:
        path = Path(skill_dir) / pattern
        if path.exists():
            existing_files.append(pattern)
    session_info["existing_files"] = existing_files

    log_session(skill_dir, session_num, "started", {
        "is_resume": session_info["is_resume"],
    })

    return session_info


# ---------------------------------------------------------------------------
# ZPD calibration
# ---------------------------------------------------------------------------

def calibrate_depth(skill_dir: str) -> int:
    """Calibrate the depth for the next session based on progress.

    Returns session number to start (1-6).
    """
    progress = load_progress(skill_dir)
    completed = progress.get("completed_sessions", [])

    # Find first incomplete session
    for i in range(1, 7):
        if i not in completed:
            return i

    return 0  # All complete


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def get_status(skill_dir: str) -> dict:
    """Get full status of the teach workspace."""
    progress = load_progress(skill_dir)
    completed = progress.get("completed_sessions", [])

    sessions_status = {}
    for num, info in SESSIONS.items():
        sessions_status[num] = {
            "name": info["name"],
            "completed": num in completed,
            "is_current": num == progress.get("current_session", 1),
        }

    return {
        "current_session": progress.get("current_session", 1),
        "completed": len(completed),
        "total": 6,
        "progress_pct": round(len(completed) / 6 * 100),
        "sessions": sessions_status,
        "started_at": progress.get("started_at"),
        "last_activity": progress.get("last_activity"),
    }


def print_status(skill_dir: str) -> None:
    """Print formatted status."""
    status = get_status(skill_dir)

    print(f"\n{'='*50}")
    print(f"  TEACH MODE — {status['completed']}/{status['total']} sessões ({status['progress_pct']}%)")
    print(f"{'='*50}")

    for num, info in status["sessions"].items():
        mark = "✅" if info["completed"] else ("→ " if info["is_current"] else "  ")
        print(f"  {mark} Sessão {num}: {info['name']}")

    print(f"{'='*50}\n")
