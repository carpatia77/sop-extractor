#!/usr/bin/env python3
"""Tests for scripts/teach/ — session manager + 6 sessions.

Tests: session lifecycle, progress tracking, file creation, prompts.
"""
import json
import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from teach.session_manager import (
    load_progress,
    get_completed_sessions,
    complete_session,
    start_session,
    calibrate_depth,
    get_status,
    SESSIONS,
)
from teach.session_1_pergunta import create_task_contract, load_task_contract, generate_pergunta_prompt
from teach.session_2_contexto import create_context_questions, load_context_questions
from teach.session_3_analise import run_coherence_check
from teach.session_4_sintese import create_candidates_file, create_emerging_questions
from teach.session_5_conclusoes import load_candidates, filter_approved, publish_semantic_field
from teach.session_6_aplicacao import create_application_log, load_application_log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def skill_dir(tmp_path):
    """Create a temporary skill directory."""
    d = tmp_path / "test_skill"
    d.mkdir()
    return str(d)


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_initial_progress(self, skill_dir):
        progress = load_progress(skill_dir)
        assert progress["current_session"] == 1
        assert progress["completed_sessions"] == []

    def test_complete_session_1(self, skill_dir):
        next_session = complete_session(skill_dir, 1)
        assert next_session == 2
        assert 1 in get_completed_sessions(skill_dir)

    def test_complete_all_sessions(self, skill_dir):
        for i in range(1, 7):
            next_session = complete_session(skill_dir, i)
        assert next_session == 0  # All done
        assert len(get_completed_sessions(skill_dir)) == 6

    def test_start_session(self, skill_dir):
        info = start_session(skill_dir, 1)
        assert info["session_number"] == 1
        assert info["name"] == "Pergunta"

    def test_calibrate_depth(self, skill_dir):
        assert calibrate_depth(skill_dir) == 1
        complete_session(skill_dir, 1)
        assert calibrate_depth(skill_dir) == 2

    def test_get_status(self, skill_dir):
        status = get_status(skill_dir)
        assert status["total"] == 6
        assert status["completed"] == 0
        assert status["progress_pct"] == 0

    def test_invalid_session_number(self, skill_dir):
        with pytest.raises(ValueError):
            start_session(skill_dir, 0)
        with pytest.raises(ValueError):
            start_session(skill_dir, 7)

    def test_session_definitions_complete(self):
        assert len(SESSIONS) == 6
        for i in range(1, 7):
            assert i in SESSIONS
            assert "name" in SESSIONS[i]
            assert "description" in SESSIONS[i]


# ---------------------------------------------------------------------------
# Session 1: Pergunta
# ---------------------------------------------------------------------------

class TestSession1:
    def test_create_task_contract(self, skill_dir):
        contract = create_task_contract(skill_dir, "Understand volatility drag")
        assert contract["user_goal"] == "Understand volatility drag"
        assert contract["session"] == 1

    def test_load_task_contract(self, skill_dir):
        create_task_contract(skill_dir, "test goal")
        loaded = load_task_contract(skill_dir)
        assert loaded is not None
        assert loaded["user_goal"] == "test goal"

    def test_load_nonexistent(self, skill_dir):
        assert load_task_contract(skill_dir) is None

    def test_prompt_no_existing(self, skill_dir):
        prompt = generate_pergunta_prompt(skill_dir)
        assert "Sessão 1" in prompt
        assert "?" in prompt

    def test_prompt_with_existing(self, skill_dir):
        create_task_contract(skill_dir, "existing goal")
        prompt = generate_pergunta_prompt(skill_dir)
        assert "já iniciada" in prompt


# ---------------------------------------------------------------------------
# Session 2: Contexto
# ---------------------------------------------------------------------------

class TestSession2:
    def test_create_context_questions(self, skill_dir):
        ctx = create_context_questions(skill_dir, author="Sharpe")
        assert ctx["author"] == "Sharpe"
        assert ctx["session"] == 2

    def test_load_context_questions(self, skill_dir):
        create_context_questions(skill_dir, author="test")
        loaded = load_context_questions(skill_dir)
        assert loaded is not None
        assert loaded["author"] == "test"


# ---------------------------------------------------------------------------
# Session 3: Análise
# ---------------------------------------------------------------------------

class TestSession3:
    def test_coherence_check_no_compilation(self, skill_dir):
        result = run_coherence_check(skill_dir)
        assert "error" in result

    def test_coherence_check_with_compilation(self, skill_dir):
        comp_dir = os.path.join(skill_dir, "compilation")
        os.makedirs(comp_dir)
        # Create a compilation with a contradiction
        data = {
            "principles": [
                {"statement": "Test", "refutation": {"dissent_type": "contradicts"}},
            ]
        }
        with open(os.path.join(comp_dir, "test.json"), "w") as f:
            json.dump(data, f)
        result = run_coherence_check(skill_dir)
        assert result["contradictions_found"] == 1


# ---------------------------------------------------------------------------
# Session 4: Síntese
# ---------------------------------------------------------------------------

class TestSession4:
    def test_create_candidates_file(self, skill_dir):
        candidates = [{"type": "concept", "term": "Volatility Drag"}]
        path = create_candidates_file(skill_dir, candidates)
        assert path.exists()

    def test_create_emerging_questions(self, skill_dir):
        questions = ["What is the relationship between X and Y?"]
        path = create_emerging_questions(skill_dir, questions)
        assert path.exists()


# ---------------------------------------------------------------------------
# Session 5: Conclusões
# ---------------------------------------------------------------------------

class TestSession5:
    def test_load_candidates_empty(self, skill_dir):
        assert load_candidates(skill_dir) == []

    def test_filter_approved(self):
        candidates = [
            {"status": "approved", "term": "A"},
            {"status": "rejected", "term": "B"},
            {"status": "approved", "term": "C"},
        ]
        approved = filter_approved(candidates)
        assert len(approved) == 2

    def test_publish_semantic_field(self, skill_dir):
        approved = [
            {"type": "concept", "term": "Test", "status": "approved"},
            {"type": "edge", "source": "a", "target": "b", "status": "approved"},
        ]
        path = publish_semantic_field(skill_dir, approved)
        assert path.exists()
        with open(path) as f:
            sf = json.load(f)
        assert sf["metadata"]["total_nodes"] == 1
        assert sf["metadata"]["total_edges"] == 1


# ---------------------------------------------------------------------------
# Session 6: Aplicação
# ---------------------------------------------------------------------------

class TestSession6:
    def test_create_application_log(self, skill_dir):
        log = create_application_log(skill_dir, applied_actions=["Read chapter 1"])
        assert log["applied_actions"] == ["Read chapter 1"]
        assert log["session"] == 6

    def test_load_application_log(self, skill_dir):
        create_application_log(skill_dir, reflection="Good session")
        loaded = load_application_log(skill_dir)
        assert loaded is not None
        assert loaded["reflection"] == "Good session"
