from validate_architecture_audit import (
    split_front_matter,
    find_claim_lines,
    seals_on_line,
    check_seal_gate,
    check_grounding_gate,
    check_intent_gate,
    check_non_contamination_gate,
    collect_observed_ids,
    run_validation,
)

GOOD_ARTIFACT = """---
intent: reverse-engineering
approved_by: jane
analyst_lens: quantitative-systems-architect
system: ASG
---

# ASG — reverse-engineered architecture

## Frontend observations
- [OBSERVED O1 part1/03:12] The dashboard shows a volume-profile chart on the right.
- [OBSERVED O2 part2/21:40] A green "signal" marker appears at the value area edge.

## Inferred backend
- [INFERRED I1 ← O1, O2] The backend maintains a running TPO histogram and emits a
  signal when price re-enters the value area.
"""


def write(tmp_path, text, name="asg_architecture.md"):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return str(f)


def test_split_front_matter_parses_fenced_block():
    front, body = split_front_matter(GOOD_ARTIFACT)
    assert front["intent"] == "reverse-engineering"
    assert front["approved_by"] == "jane"
    assert front["analyst_lens"] == "quantitative-systems-architect"
    assert "OBSERVED O1" in body
    assert "intent:" not in body  # front matter stripped from body


def test_split_front_matter_absent_returns_empty():
    front, body = split_front_matter("no front matter here\n- [OBSERVED O1 s/1] x")
    assert front == {}
    assert "OBSERVED O1" in body


def test_find_claim_lines_only_bullets():
    body = "# heading\nprose line\n- bullet claim\n* another claim\n\n| table | row |"
    claims = find_claim_lines(body)
    texts = [c[1] for c in claims]
    assert any("bullet claim" in t for t in texts)
    assert any("another claim" in t for t in texts)
    assert not any("heading" in t for t in texts)
    assert not any("table" in t for t in texts)


def test_seals_on_line_detects_both_kinds():
    assert seals_on_line("- [OBSERVED O1 s/1] x")[0][0] == "OBSERVED"
    assert seals_on_line("- [INFERRED I1 ← O1] y")[0][0] == "INFERRED"
    assert seals_on_line("- no seal here") == []


def test_good_artifact_passes_all_gates(tmp_path):
    path = write(tmp_path, GOOD_ARTIFACT)
    assert run_validation(path) == 0


# --- Seal Gate --------------------------------------------------------------

def test_seal_gate_fails_on_unsealed_claim():
    body = "- [OBSERVED O1 s/1] fine\n- this claim has no seal at all"
    ok, errors = check_seal_gate(body)
    assert not ok
    assert any("no [OBSERVED" in e for e in errors)


def test_seal_gate_fails_on_double_seal():
    body = "- [OBSERVED O1 s/1] and also [INFERRED I1 ← O1] on one line"
    ok, errors = check_seal_gate(body)
    assert not ok
    assert any("2 seals" in e for e in errors)


def test_unsealed_line_fails_full_validation(tmp_path):
    bad = GOOD_ARTIFACT + "\n- an unsealed assertion sneaks in here\n"
    path = write(tmp_path, bad)
    assert run_validation(path) == 1


# --- Grounding Gate ---------------------------------------------------------

def test_grounding_gate_fails_when_inferred_has_no_observed():
    body = "- [OBSERVED O1 s/1] x\n- [INFERRED I1 ← ] a hypothesis with empty citation"
    ok, errors = check_grounding_gate(body)
    assert not ok
    assert any("no cited OBSERVED" in e for e in errors)


def test_grounding_gate_fails_on_dangling_observed_id():
    body = "- [OBSERVED O1 s/1] x\n- [INFERRED I1 ← O9] cites an id that does not exist"
    ok, errors = check_grounding_gate(body)
    assert not ok
    assert any("O9" in e for e in errors)


def test_grounding_gate_is_persona_blind(tmp_path):
    """A densely-argued inference with no cited observation fails the same as a
    naive one — the analyst_lens never exempts a line from needing evidence."""
    bad = """---
intent: reverse-engineering
approved_by: jane
analyst_lens: quantitative-systems-architect
system: ASG
---
- [OBSERVED O1 part1/01:00] The UI shows a number.
- [INFERRED I1 ← O7] As any quant architect knows, the engine surely runs a Kalman filter.
"""
    path = write(tmp_path, bad)
    assert run_validation(path) == 1


# --- Intent Gate ------------------------------------------------------------

def test_intent_gate_requires_reverse_engineering():
    ok, errors = check_intent_gate({"intent": "summary", "approved_by": "x", "analyst_lens": "y"})
    assert not ok
    assert any("intent" in e for e in errors)


def test_intent_gate_requires_approver():
    ok, errors = check_intent_gate({"intent": "reverse-engineering", "analyst_lens": "y"})
    assert not ok
    assert any("approved_by" in e for e in errors)


def test_intent_gate_requires_analyst_lens():
    ok, errors = check_intent_gate({"intent": "reverse-engineering", "approved_by": "x"})
    assert not ok
    assert any("analyst_lens" in e for e in errors)


def test_missing_analyst_lens_fails_full_validation(tmp_path):
    bad = GOOD_ARTIFACT.replace("analyst_lens: quantitative-systems-architect\n", "")
    path = write(tmp_path, bad)
    assert run_validation(path) == 1


# --- Non-Contamination Gate -------------------------------------------------

def test_non_contamination_gate_skipped_without_skill_dir():
    ok, errors, skipped = check_non_contamination_gate(None)
    assert ok and skipped


def test_non_contamination_gate_fails_when_inferred_in_core(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "first_principles.md").write_text(
        "- A real principle.\n- [INFERRED I1 ← O1] this must not be here\n", encoding="utf-8")
    ok, errors, skipped = check_non_contamination_gate(str(skill))
    assert not ok and not skipped
    assert any("first_principles.md" in e for e in errors)


def test_non_contamination_gate_passes_clean_core(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "sops.md").write_text("### SOP: do the thing\n1. step one\n", encoding="utf-8")
    ok, errors, skipped = check_non_contamination_gate(str(skill))
    assert ok and not skipped


def test_full_validation_with_contaminated_core_fails(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("- [INFERRED I1 ← O1] leaked into the core\n", encoding="utf-8")
    path = write(skill, GOOD_ARTIFACT)
    assert run_validation(path, skill_dir=str(skill)) == 1


def test_collect_observed_ids():
    body = "- [OBSERVED O1 s/1] a\n- [OBSERVED O2 s/2] b\n- [INFERRED I1 ← O1] c"
    assert collect_observed_ids(body) == {"O1", "O2"}
